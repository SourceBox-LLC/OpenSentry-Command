"""
Persistent RTSP camera stream management for OpenSentry Command Center.
"""
import cv2
import threading
import time
import os
import hashlib
from urllib.parse import urlparse, urlunparse

from ..models.camera import CAMERAS, cameras_lock
from ..config import Config

# Force RTSP to use TCP and accept self-signed certs for RTSPS
# tls_verify=0 allows self-signed certificates
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|rtsp_flags;prefer_tcp|tls_verify;0"


def derive_credential(secret: str, service: str) -> str:
    """Derive a credential from a secret and service name using SHA256"""
    input_str = f"{secret}:{service}"
    hash_bytes = hashlib.sha256(input_str.encode()).hexdigest()
    return hash_bytes[:32]


def _get_rtsp_credentials():
    """Get RTSP credentials (derived or legacy)"""
    if Config.OPENSENTRY_SECRET:
        print("[RTSP] Using derived credentials from OPENSENTRY_SECRET")
        return "opensentry", derive_credential(Config.OPENSENTRY_SECRET, "rtsp")
    else:
        print(f"[RTSP] Using legacy credentials: {Config.RTSP_USERNAME}/{'*' * len(Config.RTSP_PASSWORD)}")
        return Config.RTSP_USERNAME, Config.RTSP_PASSWORD


RTSP_USERNAME, RTSP_PASSWORD = _get_rtsp_credentials()


def add_rtsp_credentials(url: str) -> str:
    """Add authentication credentials to RTSP URL if not already present"""
    parsed = urlparse(url)
    if parsed.username is None and RTSP_USERNAME and RTSP_PASSWORD:
        netloc = f"{RTSP_USERNAME}:{RTSP_PASSWORD}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    return url


class CameraStream:
    """Manages a persistent RTSP connection with shared frame buffer"""
    
    def __init__(self, camera_id: str, url: str):
        self.camera_id = camera_id
        self.original_url = url
        self.url = add_rtsp_credentials(url)
        masked_url = self.url.replace(f":{RTSP_PASSWORD}@", ":****@") if RTSP_PASSWORD else self.url
        print(f"[Camera {camera_id}] RTSP URL: {masked_url}")
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.connected = False
        self.thread = None
        self.last_frame_time = 0
        self.retry_count = 0
        self.max_retries = 60
        
        # Recording state
        self.recording = False
        self.recording_lock = threading.Lock()
        self.video_writer = None
        self.recording_filename = None
        self.recording_tempfile = None
        self.recording_start_time = None
        self.frames_recorded = 0
        
    def start(self):
        """Start the capture thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print(f"[Camera {self.camera_id}] Capture thread started")
        
    def stop(self):
        """Stop the capture thread"""
        self.stop_recording()  # Stop any active recording
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print(f"[Camera {self.camera_id}] Capture thread stopped")
    
    def start_recording(self) -> dict:
        """Start recording video to temporary file"""
        import tempfile
        
        with self.recording_lock:
            if self.recording:
                return {'error': 'Already recording', 'filename': self.recording_filename}
            
            if self.frame is None:
                return {'error': 'No frame available to determine video size'}
            
            # Get frame dimensions
            height, width = self.frame.shape[:2]
            
            # Create filename with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.recording_filename = f"{self.camera_id}_{timestamp}.mp4"
            
            # Use temp directory for recording
            self.recording_tempfile = tempfile.NamedTemporaryFile(
                suffix='.mp4', delete=False
            )
            filepath = self.recording_tempfile.name
            self.recording_tempfile.close()
            
            # Use mp4v codec for compatibility
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(filepath, fourcc, 15.0, (width, height))
            
            if not self.video_writer.isOpened():
                self.video_writer = None
                self.recording_filename = None
                os.unlink(filepath)
                return {'error': 'Failed to create video writer'}
            
            self.recording = True
            self.recording_start_time = time.time()
            self.frames_recorded = 0
            print(f"[Recording] Started: {self.recording_filename} (temp: {filepath})")
            
            return {
                'success': True,
                'filename': self.recording_filename,
                'camera_id': self.camera_id
            }
    
    def stop_recording(self) -> dict:
        """Stop recording and return video data"""
        with self.recording_lock:
            if not self.recording:
                return {'error': 'Not recording'}
            
            self.recording = False
            filename = self.recording_filename
            frames = self.frames_recorded
            duration = time.time() - self.recording_start_time if self.recording_start_time else 0
            temp_path = self.recording_tempfile.name if self.recording_tempfile else None
            
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            
            # Read video data from temp file
            video_data = None
            if temp_path and os.path.exists(temp_path):
                with open(temp_path, 'rb') as f:
                    video_data = f.read()
                os.unlink(temp_path)  # Delete temp file
            
            self.recording_filename = None
            self.recording_start_time = None
            self.frames_recorded = 0
            self.recording_tempfile = None
            
            print(f"[Recording] Stopped: {filename} ({frames} frames, {duration:.1f}s, {len(video_data) if video_data else 0} bytes)")
            
            return {
                'success': True,
                'filename': filename,
                'frames': frames,
                'duration': round(duration, 1),
                'data': video_data
            }
    
    def get_recording_status(self) -> dict:
        """Get current recording status"""
        with self.recording_lock:
            if not self.recording:
                return {'recording': False}
            
            duration = time.time() - self.recording_start_time if self.recording_start_time else 0
            return {
                'recording': True,
                'filename': self.recording_filename,
                'frames': self.frames_recorded,
                'duration': round(duration, 1)
            }
        
    def _capture_loop(self):
        """Background thread that maintains persistent RTSP connection"""
        while self.running:
            with cameras_lock:
                camera_info = CAMERAS.get(self.camera_id, {})
                if camera_info.get('status') == 'offline':
                    print(f"[Camera {self.camera_id}] Camera offline, stopping reconnection attempts")
                    self.running = False
                    break
            
            if self.retry_count >= self.max_retries:
                print(f"[Camera {self.camera_id}] Max retries reached, stopping")
                self.running = False
                break
            
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
            
            if not cap.isOpened():
                self.retry_count += 1
                self.connected = False
                wait_time = min(5 * self.retry_count, 30)
                print(f"[Camera {self.camera_id}] Failed to connect (attempt {self.retry_count}/{self.max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            self.retry_count = 0
            print(f"[Camera {self.camera_id}] Connected to RTSP stream")
            self.connected = True
            consecutive_failures = 0
            
            while self.running and consecutive_failures < 30:
                success, frame = cap.read()
                if success:
                    consecutive_failures = 0
                    with self.frame_lock:
                        self.frame = frame
                        self.last_frame_time = time.time()
                    
                    # Write frame to recording if active
                    with self.recording_lock:
                        if self.recording and self.video_writer:
                            self.video_writer.write(frame)
                            self.frames_recorded += 1
                else:
                    consecutive_failures += 1
                    time.sleep(0.033)
                    
            cap.release()
            self.connected = False
            if self.running:
                self.retry_count += 1
                print(f"[Camera {self.camera_id}] Connection lost, reconnecting...")
                time.sleep(1)
                
    def get_frame(self):
        """Get the latest frame (thread-safe)"""
        with self.frame_lock:
            return self.frame.copy() if self.frame is not None else None
            
    def is_active(self) -> bool:
        """Check if we have recent frames"""
        return self.connected and (time.time() - self.last_frame_time) < 2
