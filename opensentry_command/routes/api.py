"""
API routes for OpenSentry Command Center.
Handles REST API endpoints for camera data and commands.
"""
import io
import cv2
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, send_file
from flask_login import login_required, current_user

from ..models.camera import CAMERAS, camera_streams
from ..models.database import db, Media, Camera as CameraModel, AuditLog
from ..services import mqtt

api_bp = Blueprint('api', __name__)


@api_bp.route('/cameras')
@login_required
def get_cameras():
    """Get all cameras with their current status"""
    if CAMERAS:
        print(f"[API] Returning {len(CAMERAS)} cameras: {list(CAMERAS.keys())}")
    return jsonify(CAMERAS)


@api_bp.route('/camera/<camera_id>/status')
@login_required
def get_camera_status(camera_id):
    """Get status of a specific camera"""
    if camera_id in CAMERAS:
        return jsonify({
            'camera_id': camera_id,
            'status': CAMERAS[camera_id]['status'],
            'last_seen': CAMERAS[camera_id]['last_seen']
        })
    return jsonify({'error': 'Camera not found'}), 404


@api_bp.route('/camera/<camera_id>/command', methods=['POST'])
@login_required
def send_camera_command(camera_id):
    """Send command to a camera node via MQTT"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    data = request.get_json()
    command = data.get('command') if data else None
    
    if command not in ['start', 'stop', 'shutdown']:
        return jsonify({'error': 'Invalid command. Use: start, stop, shutdown'}), 400
    
    if mqtt.send_command(camera_id, command):
        return jsonify({
            'success': True,
            'camera_id': camera_id,
            'command': command
        })
    else:
        return jsonify({'error': 'Failed to send command'}), 500


@api_bp.route('/camera/<camera_id>/snapshot', methods=['GET', 'POST'])
@login_required
def take_snapshot(camera_id):
    """Capture a snapshot from a camera"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    if camera_id not in camera_streams:
        return jsonify({'error': 'Camera stream not available'}), 503
    
    stream = camera_streams[camera_id]
    frame = stream.get_frame()
    
    if frame is None:
        return jsonify({'error': 'No frame available'}), 503
    
    # Encode frame to JPEG
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    image_data = buffer.tobytes()
    
    # Check if user wants to save or just view
    save = request.args.get('save', 'false').lower() == 'true'
    
    if save:
        # Save snapshot to database as blob
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{camera_id}_{timestamp}.jpg"
        
        camera_db = CameraModel.query.filter_by(camera_id=camera_id).first()
        media = Media(
            camera_id=camera_db.id if camera_db else None,
            media_type='snapshot',
            filename=filename,
            mimetype='image/jpeg',
            data=image_data,
            size=len(image_data)
        )
        db.session.add(media)
        db.session.commit()
        
        print(f"[Snapshot] Saved to DB: {filename} ({len(image_data)} bytes)")
        
        return jsonify({
            'success': True,
            'camera_id': camera_id,
            'filename': filename,
            'id': media.id,
            'path': f'/api/snapshots/{media.id}'
        })
    else:
        # Return image directly
        return Response(image_data, mimetype='image/jpeg')


@api_bp.route('/snapshots')
@login_required
def list_snapshots():
    """List all saved snapshots from database"""
    media_list = Media.query.filter_by(media_type='snapshot').order_by(Media.created_at.desc()).all()
    return jsonify([m.to_dict() for m in media_list])


@api_bp.route('/snapshots/<int:media_id>')
@login_required
def get_snapshot(media_id):
    """Download a specific snapshot from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != 'snapshot':
        return jsonify({'error': 'Snapshot not found'}), 404
    
    return send_file(
        io.BytesIO(media.data),
        mimetype=media.mimetype,
        as_attachment=False,
        download_name=media.filename
    )


@api_bp.route('/snapshots/<int:media_id>', methods=['DELETE'])
@login_required
def delete_snapshot(media_id):
    """Delete a snapshot from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != 'snapshot':
        return jsonify({'error': 'Snapshot not found'}), 404
    
    filename = media.filename
    db.session.delete(media)
    db.session.commit()
    
    print(f"[Snapshot] Deleted from DB: {filename}")
    return jsonify({'success': True, 'deleted': filename})


# =============================================================================
# RECORDING ENDPOINTS
# =============================================================================

@api_bp.route('/camera/<camera_id>/recording/start', methods=['POST'])
@login_required
def start_recording(camera_id):
    """Start recording video from a camera"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    if camera_id not in camera_streams:
        return jsonify({'error': 'Camera stream not available'}), 503
    
    stream = camera_streams[camera_id]
    result = stream.start_recording()
    
    if 'error' in result:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/camera/<camera_id>/recording/stop', methods=['POST'])
@login_required
def stop_recording(camera_id):
    """Stop recording video from a camera and save to database"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    if camera_id not in camera_streams:
        return jsonify({'error': 'Camera stream not available'}), 503
    
    stream = camera_streams[camera_id]
    result = stream.stop_recording()
    
    if 'error' in result:
        return jsonify(result), 400
    
    # Save recording to database as blob
    if result.get('success') and result.get('data'):
        video_data = result.pop('data')  # Remove data from response
        
        camera_db = CameraModel.query.filter_by(camera_id=camera_id).first()
        media = Media(
            camera_id=camera_db.id if camera_db else None,
            media_type='recording',
            filename=result['filename'],
            mimetype='video/mp4',
            data=video_data,
            size=len(video_data),
            duration=result.get('duration')
        )
        db.session.add(media)
        db.session.commit()
        
        result['id'] = media.id
        result['path'] = f'/api/recordings/{media.id}'
        print(f"[Recording] Saved to DB: {result['filename']} ({len(video_data)} bytes)")
    
    return jsonify(result)


@api_bp.route('/camera/<camera_id>/recording/status')
@login_required
def recording_status(camera_id):
    """Get recording status for a camera"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    if camera_id not in camera_streams:
        return jsonify({'error': 'Camera stream not available', 'recording': False}), 200
    
    stream = camera_streams[camera_id]
    return jsonify(stream.get_recording_status())


@api_bp.route('/recordings')
@login_required
def list_recordings():
    """List all saved recordings from database"""
    media_list = Media.query.filter_by(media_type='recording').order_by(Media.created_at.desc()).all()
    return jsonify([m.to_dict() for m in media_list])


@api_bp.route('/recordings/<int:media_id>')
@login_required
def get_recording(media_id):
    """Download a specific recording from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != 'recording':
        return jsonify({'error': 'Recording not found'}), 404
    
    return send_file(
        io.BytesIO(media.data),
        mimetype=media.mimetype,
        as_attachment=True,
        download_name=media.filename
    )


@api_bp.route('/recordings/<int:media_id>', methods=['DELETE'])
@login_required
def delete_recording(media_id):
    """Delete a recording from database"""
    media = Media.query.get(media_id)
    if not media or media.media_type != 'recording':
        return jsonify({'error': 'Recording not found'}), 404
    
    filename = media.filename
    db.session.delete(media)
    db.session.commit()
    
    print(f"[Recording] Deleted from DB: {filename}")
    return jsonify({'success': True, 'deleted': filename})


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
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@api_bp.route('/users')
@login_required
@admin_required
def list_users():
    """List all users (admin only)"""
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'is_active': u.is_active,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'last_login': u.last_login.isoformat() if u.last_login else None
    } for u in users])


@api_bp.route('/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Create a new user (admin only)"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'viewer')
    
    if not username or len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if not password or len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if role not in ['admin', 'viewer']:
        return jsonify({'error': 'Role must be admin or viewer'}), 400
    
    # Check if username already exists
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    print(f"[Users] Created user: {username} (role: {role})")
    return jsonify({'success': True, 'id': user.id, 'username': username})


@api_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id):
    """Update a user (admin only)"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Update password if provided
    if 'password' in data and data['password']:
        if len(data['password']) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        user.set_password(data['password'])
    
    # Update role if provided
    if 'role' in data:
        if data['role'] not in ['admin', 'viewer']:
            return jsonify({'error': 'Role must be admin or viewer'}), 400
        # Prevent removing last admin
        if user.role == 'admin' and data['role'] != 'admin':
            admin_count = User.query.filter_by(role='admin').count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot remove the last admin'}), 400
        user.role = data['role']
    
    # Update active status if provided
    if 'is_active' in data:
        # Prevent disabling last admin
        if user.role == 'admin' and not data['is_active']:
            active_admin_count = User.query.filter_by(role='admin', is_active=True).count()
            if active_admin_count <= 1:
                return jsonify({'error': 'Cannot disable the last active admin'}), 400
        user.is_active = data['is_active']
    
    db.session.commit()
    print(f"[Users] Updated user: {user.username}")
    return jsonify({'success': True, 'username': user.username})


@api_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user (admin only)"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    # Prevent deleting last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            return jsonify({'error': 'Cannot delete the last admin'}), 400
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    print(f"[Users] Deleted user: {username}")
    return jsonify({'success': True, 'deleted': username})


# =============================================================================
# AUDIT LOG ENDPOINTS
# =============================================================================

@api_bp.route('/audit-logs')
@login_required
@admin_required
def list_audit_logs():
    """List audit logs (admin only)"""
    limit = request.args.get('limit', 100, type=int)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return jsonify([l.to_dict() for l in logs])


# =============================================================================
# CAMERA GROUPS ENDPOINTS
# =============================================================================

from ..models.database import CameraGroup

@api_bp.route('/camera-groups')
@login_required
def list_camera_groups():
    """List all camera groups"""
    groups = CameraGroup.query.all()
    return jsonify([{
        'id': g.id,
        'name': g.name,
        'color': g.color,
        'icon': g.icon,
        'camera_count': g.cameras.count()
    } for g in groups])


@api_bp.route('/camera-groups', methods=['POST'])
@login_required
@admin_required
def create_camera_group():
    """Create a new camera group (admin only)"""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    
    if CameraGroup.query.filter_by(name=data['name']).first():
        return jsonify({'error': 'Group name already exists'}), 400
    
    group = CameraGroup(
        name=data['name'],
        color=data.get('color', '#22c55e'),
        icon=data.get('icon', '📁')
    )
    db.session.add(group)
    db.session.commit()
    
    return jsonify({'success': True, 'id': group.id, 'name': group.name})


@api_bp.route('/camera-groups/<int:group_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_camera_group(group_id):
    """Delete a camera group (admin only)"""
    group = CameraGroup.query.get(group_id)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    # Unassign cameras from this group
    for camera in group.cameras:
        camera.group_id = None
    
    db.session.delete(group)
    db.session.commit()
    
    return jsonify({'success': True, 'deleted': group.name})


@api_bp.route('/camera/<camera_id>/group', methods=['PUT'])
@login_required
@admin_required
def assign_camera_group(camera_id):
    """Assign a camera to a group (admin only)"""
    camera = CameraModel.query.filter_by(camera_id=camera_id).first()
    if not camera:
        return jsonify({'error': 'Camera not found'}), 404
    
    data = request.get_json()
    group_id = data.get('group_id') if data else None
    
    if group_id:
        group = CameraGroup.query.get(group_id)
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        camera.group_id = group_id
    else:
        camera.group_id = None
    
    db.session.commit()
    return jsonify({'success': True, 'camera_id': camera_id, 'group_id': group_id})
