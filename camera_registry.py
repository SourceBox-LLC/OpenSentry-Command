"""
Shared camera registry and state management for OpenSentry Command Center.
"""
import threading

# Camera registry - starts empty, populated by mDNS discovery
CAMERAS = {}

# Lock for thread-safe camera registry updates
cameras_lock = threading.Lock()

# Global camera streams registry
camera_streams = {}
