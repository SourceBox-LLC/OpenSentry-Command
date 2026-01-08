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
from ..auth import authenticate, is_rate_limited, get_client_ip

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
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        user = authenticate(username, password)
        if user:
            login_user(user)
            session.permanent = True
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
