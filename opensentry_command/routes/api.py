"""
API routes for OpenSentry Command Center.
Handles REST API endpoints for camera data and commands.
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from ..models.camera import CAMERAS
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
