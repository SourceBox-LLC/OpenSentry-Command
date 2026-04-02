from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import AuthUser, require_view, require_admin, get_current_user
from app.models.models import Camera, CameraGroup, Media, Setting, Alert
from app.schemas.schemas import (
    CameraGroupCreate,
    CameraGroupResponse,
    MediaResponse,
    AlertResponse,
    RecordingSettings,
    NotificationSettings,
)

router = APIRouter(prefix="/api", tags=["api"])


# Camera CRUD
@router.get("/cameras")
async def list_cameras(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """List all cameras for the user's organization."""
    cameras = db.query(Camera).filter_by(org_id=user.org_id).all()
    result = [c.to_dict() for c in cameras]
    print(f"[cameras] Returning {len(result)} cameras for org {user.org_id}")
    for cam in result:
        print(f"[cameras]   - camera_id={cam.get('camera_id')}, name={cam.get('name')}")
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
        "notifications": {
            "motion_notifications": Setting.get(
                db, user.org_id, "motion_notifications", "true"
            )
            == "true",
            "face_notifications": Setting.get(
                db, user.org_id, "face_notifications", "true"
            )
            == "true",
            "object_notifications": Setting.get(
                db, user.org_id, "object_notifications", "true"
            )
            == "true",
            "toast_notifications": Setting.get(
                db, user.org_id, "toast_notifications", "true"
            )
            == "true",
        },
        "recording": {
            "motion_recording": Setting.get(
                db, user.org_id, "motion_recording", "false"
            )
            == "true",
            "face_recording": Setting.get(db, user.org_id, "face_recording", "false")
            == "true",
            "object_recording": Setting.get(
                db, user.org_id, "object_recording", "false"
            )
            == "true",
            "post_buffer": int(Setting.get(db, user.org_id, "post_buffer", "5")),
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


@router.get("/settings/notifications")
async def get_notification_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get notification settings."""
    return {
        "motion_notifications": Setting.get(
            db, user.org_id, "motion_notifications", "true"
        )
        == "true",
        "face_notifications": Setting.get(db, user.org_id, "face_notifications", "true")
        == "true",
        "object_notifications": Setting.get(
            db, user.org_id, "object_notifications", "true"
        )
        == "true",
        "toast_notifications": Setting.get(
            db, user.org_id, "toast_notifications", "true"
        )
        == "true",
    }


@router.post("/settings/notifications")
async def update_notification_settings(
    data: NotificationSettings,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update notification settings."""
    Setting.set(
        db, user.org_id, "motion_notifications", str(data.motion_notifications).lower()
    )
    Setting.set(
        db, user.org_id, "face_notifications", str(data.face_notifications).lower()
    )
    Setting.set(
        db, user.org_id, "object_notifications", str(data.object_notifications).lower()
    )
    Setting.set(
        db, user.org_id, "toast_notifications", str(data.toast_notifications).lower()
    )
    return {"success": True}


@router.get("/settings/recording")
async def get_recording_settings(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get recording settings."""
    return {
        "motion_recording": Setting.get(db, user.org_id, "motion_recording", "false")
        == "true",
        "face_recording": Setting.get(db, user.org_id, "face_recording", "false")
        == "true",
        "object_recording": Setting.get(db, user.org_id, "object_recording", "false")
        == "true",
        "post_buffer": int(Setting.get(db, user.org_id, "post_buffer", "5")),
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
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update recording settings."""
    Setting.set(db, user.org_id, "motion_recording", str(data.motion_recording).lower())
    Setting.set(db, user.org_id, "face_recording", str(data.face_recording).lower())
    Setting.set(db, user.org_id, "object_recording", str(data.object_recording).lower())
    Setting.set(db, user.org_id, "post_buffer", str(data.post_buffer))
    Setting.set(
        db, user.org_id, "scheduled_recording", str(data.scheduled_recording).lower()
    )
    Setting.set(db, user.org_id, "scheduled_start", str(data.scheduled_start))
    Setting.set(db, user.org_id, "scheduled_end", str(data.scheduled_end))
    Setting.set(db, user.org_id, "continuous_24_7", str(data.continuous_24_7).lower())
    return {"success": True}


# Alerts
@router.get("/alerts")
async def list_alerts(
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
    detection_type: str = None,
    camera_id: str = None,
    since_hours: int = 24,
    limit: int = 100,
):
    """List alerts for the user's organization."""
    query = db.query(Alert).filter_by(org_id=user.org_id)

    if detection_type:
        if detection_type not in ["motion", "face", "object"]:
            raise HTTPException(status_code=400, detail="Invalid detection type")
        query = query.filter_by(detection_type=detection_type)

    if camera_id:
        query = query.filter_by(camera_id=camera_id)

    since_time = datetime.utcnow() - timedelta(hours=since_hours)
    query = query.filter(Alert.created_at >= since_time)

    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return [a.to_dict() for a in alerts]


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: int, user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get a specific alert."""
    alert = db.query(Alert).filter_by(id=alert_id, org_id=user.org_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.to_dict()


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete an alert."""
    alert = db.query(Alert).filter_by(id=alert_id, org_id=user.org_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    db.delete(alert)
    db.commit()
    return {"success": True, "deleted": alert_id}


# Media (snapshots/recordings metadata stored in database)
@router.get("/media")
async def list_media(
    user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """List all media for the user's organization."""
    media_list = (
        db.query(Media)
        .filter_by(org_id=user.org_id)
        .order_by(Media.created_at.desc())
        .all()
    )
    return [m.to_dict() for m in media_list]


@router.get("/media/{media_id}")
async def get_media(
    media_id: int, user: AuthUser = Depends(require_view), db: Session = Depends(get_db)
):
    """Get media metadata."""
    media = db.query(Media).filter_by(id=media_id, org_id=user.org_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return media.to_dict()


@router.delete("/media/{media_id}")
async def delete_media(
    media_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete media."""
    media = db.query(Media).filter_by(id=media_id, org_id=user.org_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    db.delete(media)
    db.commit()
    return {"success": True, "deleted": media_id}


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
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "OpenSentry Command Center API"}
