"""
API routes for OpenSentry Command Center.
Handles REST API endpoints for camera data and commands.
"""

import io
import cv2
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, Response, send_file
from flask_login import login_required, current_user

from ..models.camera import CAMERAS, camera_streams
from ..models.database import db, Media, Camera as CameraModel, AuditLog, Alert
from ..services import mqtt

api_bp = Blueprint("api", __name__)


@api_bp.route("/health")
def health_check():
    """Health check endpoint for system monitoring"""
    return jsonify({"status": "healthy", "service": "OpenSentry Command Center"})


@api_bp.route("/cameras")
@login_required
def get_cameras():
    """Get all cameras with their current status"""
    if CAMERAS:
        print(f"[API] Returning {len(CAMERAS)} cameras: {list(CAMERAS.keys())}")
    return jsonify(CAMERAS)


@api_bp.route("/camera/<camera_id>/status")
@login_required
def get_camera_status(camera_id):
    """Get status of a specific camera"""
    if camera_id in CAMERAS:
        return jsonify(
            {
                "camera_id": camera_id,
                "status": CAMERAS[camera_id]["status"],
                "last_seen": CAMERAS[camera_id]["last_seen"],
            }
        )
    return jsonify({"error": "Camera not found"}), 404


@api_bp.route("/camera/<camera_id>/command", methods=["POST"])
@login_required
def send_camera_command(camera_id):
    """Send command to a camera node via MQTT"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    data = request.get_json()
    command = data.get("command") if data else None

    if command not in ["start", "stop", "shutdown"]:
        return jsonify({"error": "Invalid command. Use: start, stop, shutdown"}), 400

    if mqtt.send_command(camera_id, command):
        return jsonify({"success": True, "camera_id": camera_id, "command": command})
    else:
        return jsonify({"error": "Failed to send command"}), 500


@api_bp.route("/camera/<camera_id>/forget", methods=["DELETE"])
@login_required
def forget_camera(camera_id):
    """Forget/remove a camera node from the system"""
    from ..models.camera import cameras_lock

    # Check if camera exists
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    camera_name = CAMERAS[camera_id].get("name", camera_id)

    try:
        # Stop and remove camera stream if active
        if camera_id in camera_streams:
            camera_streams[camera_id].stop()
            del camera_streams[camera_id]

        # Remove from in-memory CAMERAS dict
        with cameras_lock:
            del CAMERAS[camera_id]

        # Remove from database
        camera_model = CameraModel.query.filter_by(camera_id=camera_id).first()
        if camera_model:
            # Also delete associated media (snapshots/recordings)
            Media.query.filter_by(camera_id=camera_model.id).delete()
            db.session.delete(camera_model)
            db.session.commit()

        # Log the action
        log_entry = AuditLog(
            event="camera_forgotten",
            username=current_user.username,
            ip_address=request.remote_addr,
            details=f"Removed camera: {camera_name} ({camera_id})",
        )
        db.session.add(log_entry)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Camera {camera_name} has been forgotten",
                "camera_id": camera_id,
            }
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to forget camera: {str(e)}"}), 500


@api_bp.route("/camera/<camera_id>/snapshot", methods=["GET", "POST"])
@login_required
def take_snapshot(camera_id):
    """Capture a snapshot from a camera"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    if camera_id not in camera_streams:
        return jsonify({"error": "Camera stream not available"}), 503

    stream = camera_streams[camera_id]
    frame = stream.get_frame()

    if frame is None:
        return jsonify({"error": "No frame available"}), 503

    # Encode frame to JPEG
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    image_data = buffer.tobytes()

    # Check if user wants to save or just view
    save = request.args.get("save", "false").lower() == "true"

    if save:
        # Save snapshot to database as blob
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{camera_id}_{timestamp}.jpg"

        camera_db = CameraModel.query.filter_by(camera_id=camera_id).first()
        media = Media(
            camera_id=camera_db.id if camera_db else None,
            media_type="snapshot",
            filename=filename,
            mimetype="image/jpeg",
            data=image_data,
            size=len(image_data),
        )
        db.session.add(media)
        db.session.commit()

        print(f"[Snapshot] Saved to DB: {filename} ({len(image_data)} bytes)")

        return jsonify(
            {
                "success": True,
                "camera_id": camera_id,
                "filename": filename,
                "id": media.id,
                "path": f"/api/snapshots/{media.id}",
            }
        )
    else:
        # Return image directly
        return Response(image_data, mimetype="image/jpeg")


@api_bp.route("/snapshots")
@login_required
def list_snapshots():
    """List all saved snapshots from database"""
    media_list = (
        Media.query.filter_by(media_type="snapshot")
        .order_by(Media.created_at.desc())
        .all()
    )
    return jsonify([m.to_dict() for m in media_list])


@api_bp.route("/snapshots/<int:media_id>")
@login_required
def get_snapshot(media_id):
    """Download a specific snapshot from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != "snapshot":
        return jsonify({"error": "Snapshot not found"}), 404

    return send_file(
        io.BytesIO(media.data),
        mimetype=media.mimetype,
        as_attachment=False,
        download_name=media.filename,
    )


@api_bp.route("/snapshots/<int:media_id>", methods=["DELETE"])
@login_required
def delete_snapshot(media_id):
    """Delete a snapshot from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != "snapshot":
        return jsonify({"error": "Snapshot not found"}), 404

    filename = media.filename
    db.session.delete(media)
    db.session.commit()

    print(f"[Snapshot] Deleted from DB: {filename}")
    return jsonify({"success": True, "deleted": filename})


# =============================================================================
# RECORDING ENDPOINTS
# =============================================================================


@api_bp.route("/camera/<camera_id>/recording/start", methods=["POST"])
@login_required
def start_recording(camera_id):
    """Start recording video from a camera"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    if camera_id not in camera_streams:
        return jsonify({"error": "Camera stream not available"}), 503

    stream = camera_streams[camera_id]
    result = stream.start_recording()

    if "error" in result:
        return jsonify(result), 400

    # Update CAMERAS with recording status
    CAMERAS[camera_id]["recording"] = True

    return jsonify(result)


@api_bp.route("/camera/<camera_id>/recording/stop", methods=["POST"])
@login_required
def stop_recording(camera_id):
    """Stop recording video from a camera and save to database"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    if camera_id not in camera_streams:
        return jsonify({"error": "Camera stream not available"}), 503

    stream = camera_streams[camera_id]
    result = stream.stop_recording()

    if "error" in result:
        return jsonify(result), 400

    # Update CAMERAS with recording status
    CAMERAS[camera_id]["recording"] = False

    # Save recording to database as blob
    if result.get("success") and result.get("data"):
        video_data = result.pop("data")  # Remove data from response

        camera_db = CameraModel.query.filter_by(camera_id=camera_id).first()
        media = Media(
            camera_id=camera_db.id if camera_db else None,
            media_type="recording",
            filename=result["filename"],
            mimetype="video/mp4",
            data=video_data,
            size=len(video_data),
            duration=result.get("duration"),
        )
        db.session.add(media)
        db.session.commit()

        result["id"] = media.id
        result["path"] = f"/api/recordings/{media.id}"
        print(
            f"[Recording] Saved to DB: {result['filename']} ({len(video_data)} bytes)"
        )

    return jsonify(result)


@api_bp.route("/camera/<camera_id>/recording/status")
@login_required
def recording_status(camera_id):
    """Get recording status for a camera"""
    if camera_id not in CAMERAS:
        return jsonify({"error": "Camera not found"}), 404

    if camera_id not in camera_streams:
        return jsonify(
            {"error": "Camera stream not available", "recording": False}
        ), 200

    stream = camera_streams[camera_id]
    return jsonify(stream.get_recording_status())


@api_bp.route("/recordings")
@login_required
def list_recordings():
    """List all saved recordings from database"""
    media_list = (
        Media.query.filter_by(media_type="recording")
        .order_by(Media.created_at.desc())
        .all()
    )
    return jsonify([m.to_dict() for m in media_list])


@api_bp.route("/recordings/<int:media_id>")
@login_required
def get_recording(media_id):
    """Stream a recording for playback (or download with ?download=true)"""
    media = Media.query.get(media_id)
    if not media or media.media_type != "recording":
        return jsonify({"error": "Recording not found"}), 404

    # Check if download is requested
    download = request.args.get("download", "false").lower() == "true"

    return send_file(
        io.BytesIO(media.data),
        mimetype=media.mimetype,
        as_attachment=download,
        download_name=media.filename if download else None,
    )


@api_bp.route("/recordings/<int:media_id>", methods=["DELETE"])
@login_required
def delete_recording(media_id):
    """Delete a recording from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != "recording":
        return jsonify({"error": "Recording not found"}), 404

    filename = media.filename
    db.session.delete(media)
    db.session.commit()

    print(f"[Recording] Deleted from DB: {filename}")
    return jsonify({"success": True, "deleted": filename})


# =============================================================================
# RECORDING SETTINGS ENDPOINTS
# =============================================================================

from ..models.database import Setting


@api_bp.route("/settings/recording", methods=["GET"])
@login_required
def get_recording_settings():
    """Get all recording settings"""
    settings = {
        # Auto-recording toggles
        "motion_recording": Setting.get("motion_recording", "false") == "true",
        "face_recording": Setting.get("face_recording", "false") == "true",
        "object_recording": Setting.get("object_recording", "false") == "true",
        # Post-detection buffer (seconds)
        "post_buffer": int(Setting.get("post_buffer", "5")),
        # Scheduled recording
        "scheduled_recording": Setting.get("scheduled_recording", "false") == "true",
        "scheduled_start": Setting.get("scheduled_start", "06:00"),
        "scheduled_end": Setting.get("scheduled_end", "17:00"),
        # 24/7 continuous recording (master toggle)
        "continuous_24_7": Setting.get("continuous_24_7", "false") == "true",
    }
    return jsonify(settings)


@api_bp.route("/settings/recording", methods=["POST"])
@login_required
def update_recording_settings():
    """Update recording settings"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Update each setting
    if "motion_recording" in data:
        Setting.set("motion_recording", str(data["motion_recording"]).lower())
    if "face_recording" in data:
        Setting.set("face_recording", str(data["face_recording"]).lower())
    if "object_recording" in data:
        Setting.set("object_recording", str(data["object_recording"]).lower())
    if "post_buffer" in data:
        Setting.set("post_buffer", str(data["post_buffer"]))
    if "scheduled_recording" in data:
        Setting.set("scheduled_recording", str(data["scheduled_recording"]).lower())
    if "scheduled_start" in data:
        Setting.set("scheduled_start", str(data["scheduled_start"]))
    if "scheduled_end" in data:
        Setting.set("scheduled_end", str(data["scheduled_end"]))
    if "continuous_24_7" in data:
        Setting.set("continuous_24_7", str(data["continuous_24_7"]).lower())

    print(f"[Settings] Recording settings updated")
    return jsonify({"success": True})


# =============================================================================
# NOTIFICATION SETTINGS ENDPOINTS
# =============================================================================


@api_bp.route("/settings/notifications", methods=["GET"])
@login_required
def get_notification_settings():
    """Get all notification settings"""
    settings = {
        "motion_notifications": Setting.get("motion_notifications", "true") == "true",
        "face_notifications": Setting.get("face_notifications", "true") == "true",
        "object_notifications": Setting.get("object_notifications", "true") == "true",
        "toast_notifications": Setting.get("toast_notifications", "true") == "true",
    }
    return jsonify(settings)


@api_bp.route("/settings/notifications", methods=["POST"])
@login_required
def update_notification_settings():
    """Update notification settings"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    if "motion_notifications" in data:
        Setting.set("motion_notifications", str(data["motion_notifications"]).lower())
    if "face_notifications" in data:
        Setting.set("face_notifications", str(data["face_notifications"]).lower())
    if "object_notifications" in data:
        Setting.set("object_notifications", str(data["object_notifications"]).lower())
    if "toast_notifications" in data:
        Setting.set("toast_notifications", str(data["toast_notifications"]).lower())

    print(f"[Settings] Notification settings updated")
    return jsonify({"success": True})


# =============================================================================
# ALL SETTINGS ENDPOINT
# =============================================================================


@api_bp.route("/settings", methods=["GET"])
@login_required
def get_all_settings():
    """Get all settings (notifications + recording)"""
    notifications = {
        "motion_notifications": Setting.get("motion_notifications", "true") == "true",
        "face_notifications": Setting.get("face_notifications", "true") == "true",
        "object_notifications": Setting.get("object_notifications", "true") == "true",
        "toast_notifications": Setting.get("toast_notifications", "true") == "true",
    }
    recording = {
        "motion_recording": Setting.get("motion_recording", "false") == "true",
        "face_recording": Setting.get("face_recording", "false") == "true",
        "object_recording": Setting.get("object_recording", "false") == "true",
        "post_buffer": int(Setting.get("post_buffer", "5")),
        "scheduled_recording": Setting.get("scheduled_recording", "false") == "true",
        "scheduled_start": Setting.get("scheduled_start", "06:00"),
        "scheduled_end": Setting.get("scheduled_end", "17:00"),
        "continuous_24_7": Setting.get("continuous_24_7", "false") == "true",
    }
    return jsonify({"notifications": notifications, "recording": recording})


# =============================================================================
# USER MANAGEMENT ENDPOINTS
# =============================================================================

from ..models.database import User


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated_function


@api_bp.route("/users")
@login_required
@admin_required
def list_users():
    """List all users (admin only)"""
    users = User.query.all()
    return jsonify(
        [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ]
    )


@api_bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    """Create a new user (admin only)"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "viewer")

    if not username or len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in ["admin", "viewer"]:
        return jsonify({"error": "Role must be admin or viewer"}), 400

    # Check if username already exists
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    print(f"[Users] Created user: {username} (role: {role})")
    return jsonify({"success": True, "id": user.id, "username": username})


@api_bp.route("/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def update_user(user_id):
    """Update a user (admin only)"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Update password if provided
    if "password" in data and data["password"]:
        if len(data["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        user.set_password(data["password"])

    # Update role if provided
    if "role" in data:
        if data["role"] not in ["admin", "viewer"]:
            return jsonify({"error": "Role must be admin or viewer"}), 400
        # Prevent removing last admin
        if user.role == "admin" and data["role"] != "admin":
            admin_count = User.query.filter_by(role="admin").count()
            if admin_count <= 1:
                return jsonify({"error": "Cannot remove the last admin"}), 400
        user.role = data["role"]

    # Update active status if provided
    if "is_active" in data:
        # Prevent disabling last admin
        if user.role == "admin" and not data["is_active"]:
            active_admin_count = User.query.filter_by(
                role="admin", is_active=True
            ).count()
            if active_admin_count <= 1:
                return jsonify({"error": "Cannot disable the last active admin"}), 400
        user.is_active = data["is_active"]

    db.session.commit()
    print(f"[Users] Updated user: {user.username}")
    return jsonify({"success": True, "username": user.username})


@api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user (admin only)"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    # Prevent deleting last admin
    if user.role == "admin":
        admin_count = User.query.filter_by(role="admin").count()
        if admin_count <= 1:
            return jsonify({"error": "Cannot delete the last admin"}), 400

    username = user.username
    db.session.delete(user)
    db.session.commit()

    print(f"[Users] Deleted user: {username}")
    return jsonify({"success": True, "deleted": username})


@api_bp.route("/users/<int:user_id>/change-password", methods=["POST"])
@login_required
def change_password(user_id):
    """Change a user's password (user can change own, admin can change any)"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Only allow user to change their own password, or admin to change any
    if user.id != current_user.id and not current_user.is_admin():
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    # Verify current password (unless admin changing another user's password)
    if user.id == current_user.id:
        if not user.check_password(current_password):
            return jsonify({"error": "Current password is incorrect"}), 400

    # Validate new password
    if not new_password:
        return jsonify({"error": "New password is required"}), 400

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match"}), 400

    # Update password
    user.set_password(new_password)
    db.session.commit()

    # Audit log
    from ..security import audit_log
    from ..auth import get_client_ip

    ip = get_client_ip()
    audit_log(
        "PASSWORD_CHANGE",
        ip,
        current_user.username,
        f"User changed password: {user.username}",
    )

    print(f"[Users] Password changed for user: {user.username}")
    return jsonify({"success": True, "message": "Password changed successfully"})


# =============================================================================
# AUDIT LOG ENDPOINTS
# =============================================================================


@api_bp.route("/audit-logs")
@login_required
@admin_required
def list_audit_logs():
    """List audit logs (admin only)"""
    limit = request.args.get("limit", 100, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return jsonify([l.to_dict() for l in logs])


# =============================================================================
# CAMERA GROUPS ENDPOINTS
# =============================================================================

from ..models.database import CameraGroup


@api_bp.route("/camera-groups")
@login_required
def list_camera_groups():
    """List all camera groups"""
    groups = CameraGroup.query.all()
    return jsonify(
        [
            {
                "id": g.id,
                "name": g.name,
                "color": g.color,
                "icon": g.icon,
                "camera_count": g.cameras.count(),
            }
            for g in groups
        ]
    )


@api_bp.route("/camera-groups", methods=["POST"])
@login_required
@admin_required
def create_camera_group():
    """Create a new camera group (admin only)"""
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400

    if CameraGroup.query.filter_by(name=data["name"]).first():
        return jsonify({"error": "Group name already exists"}), 400

    group = CameraGroup(
        name=data["name"],
        color=data.get("color", "#22c55e"),
        icon=data.get("icon", "📁"),
    )
    db.session.add(group)
    db.session.commit()

    return jsonify({"success": True, "id": group.id, "name": group.name})


@api_bp.route("/camera-groups/<int:group_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_camera_group(group_id):
    """Delete a camera group (admin only)"""
    group = CameraGroup.query.get(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404

    # Unassign cameras from this group
    for camera in group.cameras:
        camera.group_id = None

    db.session.delete(group)
    db.session.commit()

    return jsonify({"success": True, "deleted": group.name})


@api_bp.route("/camera/<camera_id>/group", methods=["PUT"])
@login_required
@admin_required
def assign_camera_group(camera_id):
    """Assign a camera to a group (admin only)"""
    camera = CameraModel.query.filter_by(camera_id=camera_id).first()
    if not camera:
        return jsonify({"error": "Camera not found"}), 404

    data = request.get_json()
    group_id = data.get("group_id") if data else None

    if group_id:
        group = CameraGroup.query.get(group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        camera.group_id = group_id
    else:
        camera.group_id = None

    db.session.commit()
    return jsonify({"success": True, "camera_id": camera_id, "group_id": group_id})


@api_bp.route("/alerts", methods=["GET"])
@login_required
def get_alerts():
    """Get detection alerts with optional filtering"""
    from ..models.database import Alert, db

    detection_type = request.args.get("type")
    since_hours = request.args.get("since_hours", 24, type=int)
    camera_id = request.args.get("camera_id")
    limit = request.args.get("limit", 100, type=int)

    query = Alert.query

    if detection_type:
        if detection_type not in ["motion", "face", "object"]:
            return jsonify({"error": "Invalid detection type"}), 400
        query = query.filter_by(detection_type=detection_type)

    if camera_id:
        query = query.filter_by(camera_id=camera_id)

    since_time = datetime.utcnow() - timedelta(hours=since_hours)
    query = query.filter(Alert.created_at >= since_time)

    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()

    return jsonify([alert.to_dict() for alert in alerts])


@api_bp.route("/alerts/<int:alert_id>", methods=["GET"])
@login_required
def get_alert(alert_id):
    """Get a specific alert"""
    from ..models.database import Alert

    alert = Alert.query.get(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    return jsonify(alert.to_dict())


@api_bp.route("/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_alert(alert_id):
    """Delete an alert (admin only)"""
    from ..models.database import Alert
    from ..security import audit_log
    from ..auth import get_client_ip

    alert = Alert.query.get(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    alert_data = alert.to_dict()
    db.session.delete(alert)
    db.session.commit()

    audit_log(
        "DELETE_ALERT",
        get_client_ip(),
        current_user.username,
        f"Deleted {alert_data['type']} alert from {alert_data['camera_id']}",
    )

    return jsonify({"success": True, "deleted": alert_id})


def log_alert(camera_id, detection_type, confidence=None, thumbnail_path=None):
    """Log a detection alert to the database"""
    from ..models.database import Alert, db

    alert = Alert(
        camera_id=camera_id,
        detection_type=detection_type,
        confidence=confidence,
        thumbnail_path=thumbnail_path,
    )
    db.session.add(alert)
    db.session.commit()

    print(f"[Alerts] Logged {detection_type} alert from {camera_id}")
    return alert
