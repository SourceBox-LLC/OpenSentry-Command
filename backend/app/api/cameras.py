import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import AuthUser, require_view, require_admin, get_current_user
from app.models.models import Camera, CameraGroup, Setting, AuditLog
from app.schemas.schemas import (
    CameraGroupCreate,
    RecordingSettings,
)

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
                n.id for n in db.query(CameraNode.id).filter(CameraNode.id.in_(node_ids)).all()
            }
            for cam in cameras:
                if cam.node_id and cam.node_id not in existing_node_ids:
                    logger.warning(
                        "Orphan camera %s (node_id=%s not found)", cam.camera_id, cam.node_id
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
async def take_snapshot(
    camera_id: str,
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
            node.node_id, "take_snapshot", {"camera_id": camera_id}, timeout=15.0,
        )
        return result
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Snapshot request timed out")
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/cameras/{camera_id}/recording")
async def toggle_recording(
    camera_id: str,
    request: Request,
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Start or stop recording on the camera node."""
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
            node.node_id, command, {"camera_id": camera_id}, timeout=10.0,
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
async def create_camera_group(
    data: CameraGroupCreate,
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
async def delete_camera_group(
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
async def assign_camera_group(
    camera_id: str,
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
    return {
        "recording": {
            "scheduled_recording": Setting.get(
                db, user.org_id, "scheduled_recording", "false"
            )
            == "true",
            "scheduled_start": Setting.get(db, user.org_id, "scheduled_start", "06:00"),
            "scheduled_end": Setting.get(db, user.org_id, "scheduled_end", "17:00"),
            "continuous_24_7": Setting.get(db, user.org_id, "continuous_24_7", "false")
            == "true",
        },
    }


@router.get("/settings/recording")
async def get_recording_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get recording settings."""
    return {
        "scheduled_recording": Setting.get(
            db, user.org_id, "scheduled_recording", "false"
        )
        == "true",
        "scheduled_start": Setting.get(db, user.org_id, "scheduled_start", "06:00"),
        "scheduled_end": Setting.get(db, user.org_id, "scheduled_end", "17:00"),
        "continuous_24_7": Setting.get(db, user.org_id, "continuous_24_7", "false")
        == "true",
    }


@router.post("/settings/recording")
async def update_recording_settings(
    data: RecordingSettings,
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
    return {"success": True}


# Audit Logs
@router.get("/audit-logs")
async def list_audit_logs(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
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

    # Verify camera belongs to this node
    camera = db.query(Camera).filter_by(camera_id=camera_id, node_id=node.id).first()
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
            "Updated node %s codec: video=%s, audio=%s", node.node_id, video_codec, camera.audio_codec
        )

    db.commit()

    logger.info("Updated codec for camera %s: video=%s, audio=%s", camera_id, video_codec, camera.audio_codec)

    return {"success": True, "message": "Codec updated"}


# ── Danger Zone ──────────────────────────────────────────────────────

@router.post("/settings/danger/wipe-logs")
async def wipe_stream_logs(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete all stream access logs for this organization."""
    if "admin" not in user.features:
        raise HTTPException(
            status_code=403,
            detail="Danger zone requires a Pro or Business plan.",
        )
    from app.models import StreamAccessLog

    count = db.query(StreamAccessLog).filter_by(org_id=user.org_id).delete()
    from app.models.models import McpActivityLog
    mcp_count = db.query(McpActivityLog).filter_by(org_id=user.org_id).delete()
    db.commit()
    logger.warning("Admin %s wiped %d stream + %d MCP logs for org %s", user.user_id, count, mcp_count, user.org_id)
    return {"success": True, "deleted_logs": count, "deleted_mcp_logs": mcp_count}


@router.post("/settings/danger/full-reset")
async def full_reset(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Full organization reset: wipe all nodes (with CloudNode notification),
    delete Tigris storage, clear stream logs, clear settings.
    """
    if "admin" not in user.features:
        raise HTTPException(
            status_code=403,
            detail="Danger zone requires a Pro or Business plan.",
        )
    from app.models import StreamAccessLog, CameraNode
    from app.services.storage import get_storage

    results = {
        "nodes_deleted": 0,
        "nodes_wiped": 0,
        "cameras_deleted": 0,
        "storage_cleaned": 0,
        "logs_deleted": 0,
        "settings_deleted": 0,
    }

    # 1. Delete all nodes (send wipe_data to each, clean Tigris, remove from DB)
    nodes = db.query(CameraNode).filter_by(org_id=user.org_id).all()
    for node in nodes:
        # Tell CloudNode to wipe local data
        try:
            from app.api.ws import manager
            result = await manager.send_command(node.node_id, "wipe_data", {}, timeout=10)
            if result and result.get("status") == "success":
                results["nodes_wiped"] += 1
        except Exception as e:
            logger.warning("Could not send wipe_data to node %s: %s", node.node_id, e)

        # Clean Tigris storage for each camera
        try:
            storage = get_storage()
            for camera in list(node.cameras):
                count = storage.delete_camera_storage(user.org_id, camera.camera_id)
                results["storage_cleaned"] += count
                results["cameras_deleted"] += 1
        except Exception as e:
            logger.warning("Storage cleanup failed for node %s: %s", node.node_id, e)

        db.delete(node)
        results["nodes_deleted"] += 1

    # 2. Wipe stream access logs
    results["logs_deleted"] = db.query(StreamAccessLog).filter_by(org_id=user.org_id).delete()

    # 3. Wipe MCP activity logs
    from app.models.models import McpActivityLog
    results["mcp_logs_deleted"] = db.query(McpActivityLog).filter_by(org_id=user.org_id).delete()

    # 4. Wipe settings
    results["settings_deleted"] = db.query(Setting).filter_by(org_id=user.org_id).delete()

    # 5. Wipe audit logs
    db.query(AuditLog).filter_by(org_id=user.org_id).delete()

    db.commit()
    logger.warning("Admin %s performed FULL RESET for org %s: %s", user.user_id, user.org_id, results)
    return {"success": True, **results}
