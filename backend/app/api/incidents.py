"""
AI-generated incident reports.

The MCP server writes here via the `create_incident`/`add_observation`/etc.
tools (see app/mcp/server.py). The dashboard reads here through the
`/api/incidents` endpoints, which are admin-only — incidents live alongside
the rest of the MCP audit surface.
"""

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_admin
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import (
    INCIDENT_SEVERITIES,
    INCIDENT_STATUSES,
    Incident,
    IncidentEvidence,
)

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------


class IncidentPatch(BaseModel):
    status: Optional[str] = Field(default=None)
    severity: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    report: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# List + counts
# ---------------------------------------------------------------------------


@router.get("")
async def list_incidents(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    camera_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    # OFFSET is O(n) — cap so no one can force SQLite to skip billions.
    offset: int = Query(default=0, ge=0, le=1_000_000),
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List incident reports for the org, newest first."""
    query = db.query(Incident).filter(Incident.org_id == user.org_id)

    if status:
        if status not in INCIDENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        query = query.filter(Incident.status == status)
    if severity:
        if severity not in INCIDENT_SEVERITIES:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        query = query.filter(Incident.severity == severity)
    if camera_id:
        query = query.filter(Incident.camera_id == camera_id)

    total = query.count()
    incidents = (
        query.order_by(Incident.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "incidents": [i.to_dict() for i in incidents],
    }


@router.get("/counts")
async def incident_counts(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Quick aggregate counts for the stat bar / badges."""
    base = db.query(Incident).filter(Incident.org_id == user.org_id)
    open_count = base.filter(Incident.status == "open").count()
    critical_open = base.filter(
        Incident.status == "open", Incident.severity == "critical"
    ).count()
    high_open = base.filter(
        Incident.status == "open", Incident.severity == "high"
    ).count()
    return {
        "open": open_count,
        "open_critical": critical_open,
        "open_high": high_open,
        "total": base.count(),
    }


# ---------------------------------------------------------------------------
# Detail / update / delete
# ---------------------------------------------------------------------------


def _get_owned_incident(db: Session, org_id: str, incident_id: int) -> Incident:
    incident = (
        db.query(Incident)
        .filter(Incident.id == incident_id, Incident.org_id == org_id)
        .first()
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/{incident_id}")
async def get_incident(
    incident_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Fetch a single incident with all of its evidence."""
    incident = _get_owned_incident(db, user.org_id, incident_id)
    return incident.to_dict(include_evidence=True)


@router.patch("/{incident_id}")
@limiter.limit("120/minute")
async def update_incident(
    request: Request,
    incident_id: int,
    patch: IncidentPatch,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Acknowledge, resolve, dismiss, or otherwise edit an incident."""
    incident = _get_owned_incident(db, user.org_id, incident_id)

    if patch.status is not None:
        if patch.status not in INCIDENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {patch.status}")
        # Mark resolution metadata when transitioning to a terminal state
        if patch.status in ("resolved", "dismissed") and incident.status not in (
            "resolved",
            "dismissed",
        ):
            incident.resolved_at = datetime.now(tz=UTC).replace(tzinfo=None)
            incident.resolved_by = f"user:{user.user_id}"
        elif patch.status == "open":
            # Re-opening clears the resolution
            incident.resolved_at = None
            incident.resolved_by = None
        incident.status = patch.status

    if patch.severity is not None:
        if patch.severity not in INCIDENT_SEVERITIES:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {patch.severity}")
        incident.severity = patch.severity

    if patch.summary is not None:
        incident.summary = patch.summary
    if patch.report is not None:
        incident.report = patch.report

    db.commit()
    db.refresh(incident)
    return incident.to_dict(include_evidence=True)


@router.delete("/{incident_id}")
@limiter.limit("60/minute")
async def delete_incident(
    request: Request,
    incident_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an incident and all of its evidence (cascades)."""
    incident = _get_owned_incident(db, user.org_id, incident_id)
    db.delete(incident)
    db.commit()
    return {"deleted": incident_id}


# ---------------------------------------------------------------------------
# Evidence — fetch a snapshot blob
# ---------------------------------------------------------------------------


@router.get("/{incident_id}/evidence/{evidence_id}")
async def get_incident_evidence(
    incident_id: int,
    evidence_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Stream a snapshot or clip blob for an evidence item.
    Returns 404 if the incident doesn't belong to the caller's org or
    if the evidence row has no binary payload."""
    # Org check via the parent incident
    _get_owned_incident(db, user.org_id, incident_id)

    evidence = (
        db.query(IncidentEvidence)
        .filter(
            IncidentEvidence.id == evidence_id,
            IncidentEvidence.incident_id == incident_id,
        )
        .first()
    )
    if not evidence or not evidence.data:
        raise HTTPException(status_code=404, detail="Evidence blob not found")

    # Strip any MIME parameters (we use video/mp2t;duration=N internally to
    # remember clip length without a schema migration — browsers don't need it).
    raw_mime = evidence.data_mime or "application/octet-stream"
    media_type = raw_mime.split(";", 1)[0].strip() or "application/octet-stream"

    return Response(
        content=evidence.data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/{incident_id}/evidence/{evidence_id}/playlist.m3u8")
async def get_incident_evidence_playlist(
    incident_id: int,
    evidence_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Synthetic single-segment HLS playlist for a clip evidence blob.
    Lets the dashboard reuse hls.js to play attach_clip captures with the
    same JWT auth as the live player. Returns 404 unless the evidence is a
    clip with attached video data."""
    _get_owned_incident(db, user.org_id, incident_id)

    evidence = (
        db.query(IncidentEvidence)
        .filter(
            IncidentEvidence.id == evidence_id,
            IncidentEvidence.incident_id == incident_id,
        )
        .first()
    )
    if not evidence or not evidence.data or evidence.kind != "clip":
        raise HTTPException(status_code=404, detail="Clip not found")

    # Pull the duration parameter back out of the stored mime, falling back
    # to a generous default that's >= max EXTINF (HLS spec requirement).
    duration = 60.0
    raw_mime = evidence.data_mime or ""
    if ";" in raw_mime:
        for param in raw_mime.split(";")[1:]:
            param = param.strip()
            if param.startswith("duration="):
                try:
                    duration = float(param.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
    target_duration = max(1, int(duration) + 1)

    # Use an absolute path for the segment so hls.js doesn't try to resolve it
    # against the playlist URL (which lives at .../playlist.m3u8 — relative
    # resolution would land in the wrong place).
    segment_url = f"/api/incidents/{incident_id}/evidence/{evidence_id}"

    playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        f"#EXT-X-TARGETDURATION:{target_duration}\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXT-X-PLAYLIST-TYPE:VOD\n"
        f"#EXTINF:{duration:.3f},\n"
        f"{segment_url}\n"
        "#EXT-X-ENDLIST\n"
    )

    return Response(
        content=playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "private, max-age=300"},
    )
