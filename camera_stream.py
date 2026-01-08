"""
Persistent RTSP camera stream management for OpenSentry Command Center.
"""
import cv2
import threading
import time
import os
import hashlib
from urllib.parse import urlparse, urlunparse

from camera_registry import CAMERAS, cameras_lock

# Force RTSP to use TCP (more stable than UDP)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


def derive_credential(secret: str, service: str) -> str:
    """Derive a credential from a secret and service name using SHA256"""
    input_str = f"{secret}:{service}"
    hash_bytes = hashlib.sha256(input_str.encode()).hexdigest()
    return hash_bytes[:32]  # First 32 chars


# RTSP authentication credentials
# Use OPENSENTRY_SECRET if set, otherwise fall back to individual credentials
OPENSENTRY_SECRET = os.environ.get("OPENSENTRY_SECRET", "")
if OPENSENTRY_SECRET:
    print("[RTSP] Using derived credentials from OPENSENTRY_SECRET")
    RTSP_USERNAME = "opensentry"
    RTSP_PASSWORD = derive_credential(OPENSENTRY_SECRET, "rtsp")
else:
    RTSP_USERNAME = os.environ.get("RTSP_USERNAME", "opensentry")
    RTSP_PASSWORD = os.environ.get("RTSP_PASSWORD", "opensentry")
    print(f"[RTSP] Using legacy credentials: {RTSP_USERNAME}/{'*' * len(RTSP_PASSWORD)}")


def add_rtsp_credentials(url: str) -> str:
    """Add authentication credentials to RTSP URL if not already present"""
    parsed = urlparse(url)
    # Only add credentials if not already present
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
        self.original_url = url  # Store original URL for comparison
        self.url = add_rtsp_credentials(url)  # URL with credentials for actual connection
        # Debug: show URL with masked password
        masked_url = self.url.replace(f":{RTSP_PASSWORD}@", ":****@") if RTSP_PASSWORD else self.url
        print(f"[Camera {camera_id}] RTSP URL: {masked_url}")
        self.frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.connected = False
        self.thread = None
        self.last_frame_time = 0
        self.retry_count = 0
        self.max_retries = 60  # Stop retrying after ~5 minutes of failures
        
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
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print(f"[Camera {self.camera_id}] Capture thread stopped")
        
    def _capture_loop(self):
        """Background thread that maintains persistent RTSP connection"""
        while self.running:
            # Check if camera is marked offline - stop retrying
            with cameras_lock:
                camera_info = CAMERAS.get(self.camera_id, {})
                if camera_info.get('status') == 'offline':
                    print(f"[Camera {self.camera_id}] Camera offline, stopping reconnection attempts")
                    self.running = False
                    break
            
            # Check retry limit
            if self.retry_count >= self.max_retries:
                print(f"[Camera {self.camera_id}] Max retries reached, stopping")
                self.running = False
                break
            
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
            
            if not cap.isOpened():
                self.retry_count += 1
                self.connected = False
                # Exponential backoff: 5s, 10s, 15s... up to 30s
                wait_time = min(5 * self.retry_count, 30)
                print(f"[Camera {self.camera_id}] Failed to connect (attempt {self.retry_count}/{self.max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            # Connected successfully - reset retry count
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
                else:
                    consecutive_failures += 1
                    time.sleep(0.033)  # ~30fps timing
                    
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
