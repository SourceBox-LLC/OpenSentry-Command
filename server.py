"""
OpenSentry Command Center - Main Flask Application
Web interface for monitoring and controlling OpenSentry camera nodes.
"""
import os
import signal
import atexit
import time

import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import modules
from camera_registry import CAMERAS, camera_streams
import mdns_discovery
import mqtt_client
import auth

app = Flask(__name__)

# Initialize authentication
auth.init_app(app)


def get_placeholder_frame(message: str = "No Signal") -> bytes:
    """Generate a placeholder frame with message"""
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(placeholder, message, (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 100), 2)
    ret, buffer = cv2.imencode('.jpg', placeholder)
    return buffer.tobytes()


def generate_frames(camera_id: str):
    """Generator function to stream frames from shared camera buffer"""
    stream = camera_streams.get(camera_id)
    
    if not stream:
        frame_bytes = get_placeholder_frame("Camera not found")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        return
    
    no_frame_count = 0
    
    while True:
        frame = stream.get_frame()
        
        if frame is not None:
            no_frame_count = 0
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
        else:
            no_frame_count += 1
            if no_frame_count > 100:  # ~3 seconds of no frames
                frame_bytes = get_placeholder_frame("Connecting...")
            else:
                time.sleep(0.033)
                continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)  # ~30fps


# =============================================================================
# Flask Routes
# =============================================================================

@app.route('/')
@login_required
def index():
    """Main page showing all cameras"""
    return render_template('index.html', cameras=CAMERAS)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    # Check if IP is rate limited before processing
    ip = auth.get_client_ip()
    limited, remaining = auth.is_rate_limited(ip)
    if limited:
        flash(f'Too many failed attempts. Try again in {remaining} seconds.', 'error')
        return render_template('login.html')
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        user = auth.authenticate(username, password)
        if user:
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            # Check if now rate limited after this attempt
            limited, remaining = auth.is_rate_limited(ip)
            if limited:
                flash(f'Account locked for {remaining} seconds due to too many failed attempts.', 'error')
            else:
                flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout and redirect to login page"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


@app.route('/video_feed/<camera_id>')
@login_required
def video_feed(camera_id):
    """Video streaming route - uses shared camera buffer"""
    if camera_id in CAMERAS:
        return Response(generate_frames(camera_id),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    return "Camera not found", 404


@app.route('/api/cameras')
@login_required
def get_cameras():
    """Get all cameras with their current status"""
    return jsonify(CAMERAS)


@app.route('/api/camera/<camera_id>/status')
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


@app.route('/api/camera/<camera_id>/command', methods=['POST'])
@login_required
def send_camera_command(camera_id):
    """Send command to a camera node via MQTT"""
    if camera_id not in CAMERAS:
        return jsonify({'error': 'Camera not found'}), 404
    
    data = request.get_json()
    command = data.get('command') if data else None
    
    if command not in ['start', 'stop', 'shutdown']:
        return jsonify({'error': 'Invalid command. Use: start, stop, shutdown'}), 400
    
    if mqtt_client.send_command(camera_id, command):
        return jsonify({
            'success': True,
            'camera_id': camera_id,
            'command': command
        })
    else:
        return jsonify({'error': 'Failed to send command'}), 500


# =============================================================================
# Application Lifecycle
# =============================================================================

def cleanup():
    """Graceful shutdown - stop all services"""
    print("\n[System] Shutting down...")
    
    # Stop all camera streams
    for camera_id, stream in camera_streams.items():
        print(f"[System] Stopping camera {camera_id}...")
        stream.stop()
    
    # Stop MQTT
    mqtt_client.stop()
    
    # Stop mDNS
    mdns_discovery.stop_discovery()
    
    print("[System] Shutdown complete")


def main():
    """Main entry point"""
    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: exit(0))
    
    # Start MQTT client
    mqtt_client.start()
    
    # Start mDNS discovery for OpenSentry nodes
    mdns_discovery.start_discovery()
    
    # Start Flask web server
    print("[Flask] Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
