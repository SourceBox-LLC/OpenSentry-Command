"""
Main routes for OpenSentry Command Center.
Handles web UI pages and video streaming.
"""
import time

import cv2
import numpy as np
from flask import Blueprint, render_template, Response, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user

from ..models.camera import CAMERAS, camera_streams
from ..auth import authenticate, is_rate_limited, get_client_ip, is_using_defaults, log_logout
from ..security import validate_csrf_token, audit_log

main_bp = Blueprint('main', __name__)


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
            if no_frame_count > 100:
                frame_bytes = get_placeholder_frame("Connecting...")
            else:
                time.sleep(0.033)
                continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.033)


@main_bp.route('/')
@login_required
def index():
    """Main page showing all cameras"""
    return render_template('index.html', cameras=CAMERAS)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    ip = get_client_ip()
    limited, remaining = is_rate_limited(ip)
    if limited:
        flash(f'Too many failed attempts. Try again in {remaining} seconds.', 'error')
        return render_template('login.html')
    
    if request.method == 'POST':
        # Validate CSRF token
        if not validate_csrf_token():
            audit_log('CSRF_FAILURE', ip, '-', 'Invalid CSRF token on login')
            flash('Security validation failed. Please try again.', 'error')
            return render_template('login.html')
        
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        user = authenticate(username, password)
        if user:
            login_user(user)
            session.permanent = True
            
            # Warn about default credentials after successful login
            if is_using_defaults():
                flash('⚠️ Security Warning: You are using default credentials. Please change them in your .env file!', 'error')
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            limited, remaining = is_rate_limited(ip)
            if limited:
                flash(f'Account locked for {remaining} seconds due to too many failed attempts.', 'error')
            else:
                flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@main_bp.route('/logout')
@login_required
def logout():
    """Logout and redirect to login page"""
    username = current_user.username if current_user else 'unknown'
    log_logout(username)
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('main.login'))


@main_bp.route('/video_feed/<camera_id>')
@login_required
def video_feed(camera_id):
    """Video streaming route - uses shared camera buffer"""
    if camera_id in CAMERAS:
        return Response(generate_frames(camera_id),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    return "Camera not found", 404


@main_bp.route('/settings')
@login_required
def settings():
    """Settings page"""
    from ..config import Config
    
    # Get the secret, mask it partially for display
    secret = Config.OPENSENTRY_SECRET or ''
    
    return render_template('settings.html', 
                          opensentry_secret=secret,
                          username=Config.OPENSENTRY_USERNAME)


@main_bp.route('/api/regenerate-secret', methods=['POST'])
@login_required
def regenerate_secret():
    """Regenerate the OPENSENTRY_SECRET and update .env file"""
    import secrets
    import os
    from ..config import Config
    from ..security import audit_log
    from ..services import camera as camera_service
    from ..models.camera import CAMERAS, camera_streams, cameras_lock
    
    ip = get_client_ip()
    
    # Generate new secret
    new_secret = secrets.token_hex(32)
    
    # Find and update .env file
    env_path = '/app/.env'  # Docker path
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    
    if not os.path.exists(env_path):
        audit_log('SECRET_REGENERATE_FAILED', ip, current_user.username, 'No .env file found')
        return {'success': False, 'error': 'No .env file found'}, 404
    
    try:
        # Read existing .env
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Update or add OPENSENTRY_SECRET
        secret_found = False
        new_lines = []
        for line in lines:
            if line.startswith('OPENSENTRY_SECRET='):
                new_lines.append(f'OPENSENTRY_SECRET={new_secret}\n')
                secret_found = True
            else:
                new_lines.append(line)
        
        if not secret_found:
            new_lines.append(f'\nOPENSENTRY_SECRET={new_secret}\n')
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        
        # Update in-memory config
        Config.OPENSENTRY_SECRET = new_secret
        os.environ['OPENSENTRY_SECRET'] = new_secret
        
        # Update RTSP credentials module-level variables
        new_username, new_password = camera_service._get_rtsp_credentials()
        camera_service.RTSP_USERNAME = new_username
        camera_service.RTSP_PASSWORD = new_password
        
        # Stop all existing camera streams and clear cameras
        with cameras_lock:
            for camera_id, stream in list(camera_streams.items()):
                print(f"[Secret Regeneration] Stopping stream for {camera_id}")
                stream.stop()
            camera_streams.clear()
            CAMERAS.clear()
            print("[Secret Regeneration] Cleared all cameras - awaiting re-discovery")
        
        audit_log('SECRET_REGENERATED', ip, current_user.username, 'Security secret regenerated successfully')
        
        return {
            'success': True, 
            'secret': new_secret,
            'message': 'Secret regenerated. Update your camera nodes with the new secret.'
        }
    
    except Exception as e:
        audit_log('SECRET_REGENERATE_FAILED', ip, current_user.username, str(e))
        return {'success': False, 'error': str(e)}, 500
