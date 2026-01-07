"""
Persistent RTSP camera stream management for OpenSentry Command Center.
"""
import cv2
import threading
import time
import os

from camera_registry import CAMERAS, cameras_lock

# Force RTSP to use TCP (more stable than UDP)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"


class CameraStream:
    """Manages a persistent RTSP connection with shared frame buffer"""
    
    def __init__(self, camera_id: str, url: str):
        self.camera_id = camera_id
        self.url = url
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
