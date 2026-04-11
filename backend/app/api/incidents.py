"""
AI-generated incident reports.

The MCP server writes here via the `create_incident`/`add_observation`/etc.
tools (see app/mcp/server.py). The dashboard reads here through the
`/api/incidents` endpoints, which are admin-only — incidents live alongside
the rest of the MCP audit surface.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_admin
from app.core.database import get_db
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
    offset: int = Query(default=0, ge=0),
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
async def update_incident(
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
            incident.resolved_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
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
async def delete_incident(
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
    """Stream a snapshot blob for an evidence item.
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

    return Response(
        content=evidence.data,
        media_type=evidence.data_mime or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=300"},
    )
