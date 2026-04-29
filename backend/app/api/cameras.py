import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_label, write_audit
from app.core.codec import sanitize_video_codec
from app.core.database import get_db
from app.core.auth import AuthUser, require_view, require_admin
from app.core.limiter import limiter
from app.models.models import Camera, CameraGroup, Setting, AuditLog
from app.schemas.schemas import (
    CameraGroupCreate,
    NotificationSettings,
    RecordingSettings,
)


# Shared defaults for notification toggles — used by the GET handler and
# the /api/settings aggregate.  Pydantic's NotificationSettings holds the
# canonical values; this dict re-expresses them as strings for Setting.get_many.
_NOTIFICATION_SETTING_DEFAULTS = {
    "motion_notifications": "true",
    "camera_transition_notifications": "true",
    "node_transition_notifications": "true",
}

router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger(__name__)


# Camera CRUD
@router.get("/cameras")
async def list_cameras(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """List all cameras for the user's organization."""
    from app.models.models import CameraNode

    cameras = db.query(Camera).filter_by(org_id=user.org_id).all()

    # Check for orphaned cameras in a single query instead of N+1
    if cameras:
        node_ids = {cam.node_id for cam in cameras if cam.node_id}
        if node_ids:
            existing_node_ids = {
                n.id
                for n in db.query(CameraNode.id)
                .filter(CameraNode.id.in_(node_ids))
                .all()
            }
            for cam in cameras:
                if cam.node_id and cam.node_id not in existing_node_ids:
                    logger.warning(
                        "Orphan camera %s (node_id=%s not found)",
                        cam.camera_id,
                        cam.node_id,
                    )

    result = [c.to_dict() for c in cameras]
    logger.debug("Returning %d cameras for org %s", len(result), user.org_id)
    return result


@router.get("/cameras/{camera_id}")
async def get_camera(
    camera_id: str,
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Get a specific camera by ID."""
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera.to_dict()


@router.post("/cameras/{camera_id}/snapshot")
@limiter.limit("30/minute")
async def take_snapshot(
    camera_id: str,
    request: Request,
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Tell the camera node to capture and store a snapshot locally."""
    from app.models.models import CameraNode
    from app.api.ws import manager

    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera.node_id:
        raise HTTPException(status_code=400, detail="Camera has no assigned node")

    node = db.query(CameraNode).filter_by(id=camera.node_id).first()
    if not node:
        raise HTTPException(status_code=400, detail="Camera node not found")
    if not manager.is_connected(node.node_id):
        raise HTTPException(status_code=503, detail="Camera node is offline")

    try:
        result = await manager.send_command(
            node.node_id,
            "take_snapshot",
            {"camera_id": camera_id},
            timeout=15.0,
        )
        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Snapshot request timed out")
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/cameras/{camera_id}/recording")
@limiter.limit("30/minute")
async def toggle_recording(
    camera_id: str,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Start or stop recording on the camera node.  Admin-only —
    recording state changes are operational decisions, not view-only."""
    from app.models.models import CameraNode
    from app.api.ws import manager

    body = await request.json()
    recording = body.get("recording", False)

    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera.node_id:
        raise HTTPException(status_code=400, detail="Camera has no assigned node")

    node = db.query(CameraNode).filter_by(id=camera.node_id).first()
    if not node:
        raise HTTPException(status_code=400, detail="Camera node not found")
    if not manager.is_connected(node.node_id):
        raise HTTPException(status_code=503, detail="Camera node is offline")

    command = "start_recording" if recording else "stop_recording"
    try:
        result = await manager.send_command(
            node.node_id,
            command,
            {"camera_id": camera_id},
            timeout=10.0,
        )
        write_audit(
            db,
            org_id=user.org_id,
            event="recording_toggled",
            user_id=user.user_id,
            username=audit_label(user),
            details={"camera_id": camera_id, "recording": bool(recording)},
            request=request,
        )
        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Recording command timed out")
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


# Camera Groups
@router.get("/camera-groups")
async def list_camera_groups(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """List all camera groups for the user's organization."""
    groups = db.query(CameraGroup).filter_by(org_id=user.org_id).all()
    return [g.to_dict() for g in groups]


@router.post("/camera-groups")
@limiter.limit("20/minute")
async def create_camera_group(
    data: CameraGroupCreate,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new camera group."""
    if db.query(CameraGroup).filter_by(org_id=user.org_id, name=data.name).first():
        raise HTTPException(status_code=400, detail="Group name already exists")

    group = CameraGroup(
        org_id=user.org_id,
        name=data.name,
        color=data.color,
        icon=data.icon,
    )
    db.add(group)
    db.commit()

    return {"success": True, "id": group.id, "name": group.name}


@router.delete("/camera-groups/{group_id}")
@limiter.limit("60/minute")
async def delete_camera_group(
    request: Request,
    group_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a camera group."""
    group = db.query(CameraGroup).filter_by(id=group_id, org_id=user.org_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    for camera in group.cameras:
        camera.group_id = None

    db.delete(group)
    db.commit()

    return {"success": True, "deleted": group.name}


@router.put("/cameras/{camera_id}/group")
@limiter.limit("60/minute")
async def assign_camera_group(
    camera_id: str,
    request: Request,
    group_id: int = None,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Assign a camera to a group."""
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if group_id:
        group = db.query(CameraGroup).filter_by(id=group_id, org_id=user.org_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        camera.group_id = group_id
    else:
        camera.group_id = None

    db.commit()
    return {"success": True, "camera_id": camera_id, "group_id": group_id}


# Settings
@router.get("/settings")
async def get_all_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get all settings for the user's organization."""
    vals = Setting.get_many(
        db,
        user.org_id,
        {
            "scheduled_recording": "false",
            "scheduled_start": "06:00",
            "scheduled_end": "17:00",
            "continuous_24_7": "false",
            **_NOTIFICATION_SETTING_DEFAULTS,
        },
    )
    return {
        "recording": {
            "scheduled_recording": vals["scheduled_recording"] == "true",
            "scheduled_start": vals["scheduled_start"],
            "scheduled_end": vals["scheduled_end"],
            "continuous_24_7": vals["continuous_24_7"] == "true",
        },
        "notifications": {
            "motion_notifications": vals["motion_notifications"] == "true",
            "camera_transition_notifications": vals["camera_transition_notifications"]
            == "true",
            "node_transition_notifications": vals["node_transition_notifications"]
            == "true",
        },
    }


@router.get("/settings/recording")
async def get_recording_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get recording settings."""
    vals = Setting.get_many(
        db,
        user.org_id,
        {
            "scheduled_recording": "false",
            "scheduled_start": "06:00",
            "scheduled_end": "17:00",
            "continuous_24_7": "false",
        },
    )
    return {
        "scheduled_recording": vals["scheduled_recording"] == "true",
        "scheduled_start": vals["scheduled_start"],
        "scheduled_end": vals["scheduled_end"],
        "continuous_24_7": vals["continuous_24_7"] == "true",
    }


@router.post("/settings/recording")
@limiter.limit("30/minute")
async def update_recording_settings(
    data: RecordingSettings,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update recording settings. Requires admin."""
    Setting.set(
        db, user.org_id, "scheduled_recording", str(data.scheduled_recording).lower()
    )
    Setting.set(db, user.org_id, "scheduled_start", str(data.scheduled_start))
    Setting.set(db, user.org_id, "scheduled_end", str(data.scheduled_end))
    Setting.set(db, user.org_id, "continuous_24_7", str(data.continuous_24_7).lower())
    write_audit(
        db,
        org_id=user.org_id,
        event="recording_settings_updated",
        user_id=user.user_id,
        username=audit_label(user),
        details={
            "scheduled_recording": bool(data.scheduled_recording),
            "scheduled_start": str(data.scheduled_start),
            "scheduled_end": str(data.scheduled_end),
            "continuous_24_7": bool(data.continuous_24_7),
        },
        request=request,
    )
    return {"success": True}


# Notification preferences — parallel to the recording settings pair.
# GET is view-level (every member needs to know what's on), POST is
# admin-only (same audit-worthy gate as the other per-org toggles).


@router.get("/settings/notifications")
async def get_notification_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Return the org's notification preferences.

    Defaults to "all on" for backward compat with orgs that existed
    before the settings UI landed — the gate only starts filtering
    after an admin explicitly flips a toggle off.
    """
    vals = Setting.get_many(db, user.org_id, _NOTIFICATION_SETTING_DEFAULTS)
    return {
        "motion_notifications": vals["motion_notifications"] == "true",
        "camera_transition_notifications": vals["camera_transition_notifications"]
        == "true",
        "node_transition_notifications": vals["node_transition_notifications"]
        == "true",
    }


@router.post("/settings/notifications")
@limiter.limit("30/minute")
async def update_notification_settings(
    data: NotificationSettings,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update notification preferences. Requires admin.

    Persists each toggle as a stringified bool so the existing Setting
    key/value table can store it without a schema change — same
    convention the recording toggles use.
    """
    Setting.set(
        db, user.org_id, "motion_notifications", str(data.motion_notifications).lower()
    )
    Setting.set(
        db,
        user.org_id,
        "camera_transition_notifications",
        str(data.camera_transition_notifications).lower(),
    )
    Setting.set(
        db,
        user.org_id,
        "node_transition_notifications",
        str(data.node_transition_notifications).lower(),
    )
    write_audit(
        db,
        org_id=user.org_id,
        event="notification_settings_updated",
        user_id=user.user_id,
        username=audit_label(user),
        details={
            "motion_notifications": bool(data.motion_notifications),
            "camera_transition_notifications": bool(
                data.camera_transition_notifications
            ),
            "node_transition_notifications": bool(data.node_transition_notifications),
        },
        request=request,
    )
    return {"success": True}


# Audit Logs
@router.get("/audit-logs")
@limiter.limit("120/minute")
async def list_audit_logs(
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
    # Capped at 500 to bound the response payload — without `le` an
    # attacker or runaway script could force a table-scan-size return.
    limit: int = Query(default=100, ge=1, le=500),
):
    """List audit logs for the user's organization."""
    logs = (
        db.query(AuditLog)
        .filter_by(org_id=user.org_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [l.to_dict() for l in logs]


# Health Check (for API endpoint health)
@router.post("/cameras/{camera_id}/codec")
@limiter.limit("30/minute")
async def report_camera_codec(
    camera_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Report video/audio codec for a camera.
    Called by CloudNode after detecting codec from first segment.
    """
    import hashlib
    from app.models.models import CameraNode

    # Verify node API key
    node_api_key = request.headers.get("X-Node-API-Key")
    if not node_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Verify camera belongs to this node AND node's org — defense-in-depth
    # against any future schema drift where camera.org_id and node.org_id
    # could diverge.  The camera_id column has a unique constraint, so
    # today this check is redundant; tomorrow it might not be.
    camera = (
        db.query(Camera)
        .filter_by(camera_id=camera_id, node_id=node.id, org_id=node.org_id)
        .first()
    )
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Parse codec info from request body
    import json

    try:
        body = await request.body()
        codec_data = json.loads(body)
        video_codec = codec_data.get("video_codec")
        audio_codec = codec_data.get("audio_codec")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    if not video_codec:
        raise HTTPException(status_code=400, detail="video_codec is required")

    # Codec strings are stored for diagnostics and MCP tool reporting —
    # reject newlines or absurd lengths to prevent playlist corruption.
    if len(video_codec) > 64 or "\n" in video_codec or "\r" in video_codec:
        raise HTTPException(status_code=400, detail="Invalid video_codec format")
    if audio_codec and (
        len(audio_codec) > 64 or "\n" in audio_codec or "\r" in audio_codec
    ):
        raise HTTPException(status_code=400, detail="Invalid audio_codec format")

    # Defensive sanitization — older CloudNode builds shipped garbage
    # H.264 codec strings (level 1.0) for the Pi's h264_v4l2m2m encoder.
    # Catch them server-side so a stale binary in the field doesn't
    # silently brick streaming again.
    video_codec = sanitize_video_codec(video_codec)

    # Update camera codec fields
    camera.video_codec = video_codec
    camera.audio_codec = audio_codec or "mp4a.40.2"  # Default to AAC-LC
    camera.codec_detected_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    # Also update node codec if this is the first camera to detect
    if node and not node.video_codec:
        node.video_codec = video_codec
        node.audio_codec = camera.audio_codec
        node.codec_detected_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        logger.info(
            "Updated node %s codec: video=%s, audio=%s",
            node.node_id,
            video_codec,
            camera.audio_codec,
        )

    db.commit()

    logger.info(
        "Updated codec for camera %s: video=%s, audio=%s",
        camera_id,
        video_codec,
        camera.audio_codec,
    )

    return {"success": True, "message": "Codec updated"}


# ── Danger Zone ──────────────────────────────────────────────────────


@router.post("/settings/danger/wipe-logs")
@limiter.limit("5/hour")
async def wipe_stream_logs(
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete all stream access logs for this organization."""
    if "admin" not in user.features:
        raise HTTPException(
            status_code=403,
            detail="Danger zone requires a Pro or Pro Plus plan.",
        )
    from app.models import StreamAccessLog

    count = db.query(StreamAccessLog).filter_by(org_id=user.org_id).delete()
    from app.models.models import McpActivityLog

    mcp_count = db.query(McpActivityLog).filter_by(org_id=user.org_id).delete()
    db.commit()
    logger.warning(
        "Admin wiped %d stream + %d MCP logs (org redacted)", count, mcp_count
    )
    write_audit(
        db,
        org_id=user.org_id,
        event="logs_wiped",
        user_id=user.user_id,
        username=audit_label(user),
        details={"stream_logs_deleted": count, "mcp_logs_deleted": mcp_count},
        request=request,
    )
    return {"success": True, "deleted_logs": count, "deleted_mcp_logs": mcp_count}


@router.post("/settings/danger/full-reset")
@limiter.limit("3/hour")
async def full_reset(
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Full organization reset: wipe all nodes (with CloudNode notification),
    clear stream logs, clear settings.
    """
    if "admin" not in user.features:
        raise HTTPException(
            status_code=403,
            detail="Danger zone requires a Pro or Pro Plus plan.",
        )
    from app.models import StreamAccessLog, CameraNode
    from app.api.hls import cleanup_camera_cache

    results = {
        "nodes_deleted": 0,
        "nodes_wiped": 0,
        "cameras_deleted": 0,
        "logs_deleted": 0,
        "settings_deleted": 0,
    }

    # 1. Delete all nodes (send wipe_data to each, clean caches, remove from DB)
    nodes = db.query(CameraNode).filter_by(org_id=user.org_id).all()
    for node in nodes:
        # Tell CloudNode to wipe local data
        try:
            from app.api.ws import manager

            result = await manager.send_command(
                node.node_id, "wipe_data", {}, timeout=10
            )
            if result and result.get("status") == "success":
                results["nodes_wiped"] += 1
        except Exception as e:
            logger.warning("Could not send wipe_data to node %s: %s", node.node_id, e)

        for camera in list(node.cameras):
            cleanup_camera_cache(camera.camera_id)
            results["cameras_deleted"] += 1

        db.delete(node)
        results["nodes_deleted"] += 1

    # 2. Wipe stream access logs
    results["logs_deleted"] = (
        db.query(StreamAccessLog).filter_by(org_id=user.org_id).delete()
    )

    # 3. Wipe MCP activity logs
    from app.models.models import McpActivityLog

    results["mcp_logs_deleted"] = (
        db.query(McpActivityLog).filter_by(org_id=user.org_id).delete()
    )

    # 4. Wipe settings
    results["settings_deleted"] = (
        db.query(Setting).filter_by(org_id=user.org_id).delete()
    )

    # 5. Wipe audit logs
    db.query(AuditLog).filter_by(org_id=user.org_id).delete()

    db.commit()
    logger.warning("Admin performed FULL RESET (org redacted): %s", results)
    write_audit(
        db,
        org_id=user.org_id,
        event="full_reset",
        user_id=user.user_id,
        username=audit_label(user),
        details=results,
        request=request,
    )
    return {"success": True, **results}
