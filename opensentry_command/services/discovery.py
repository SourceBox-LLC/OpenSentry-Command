"""
mDNS service discovery for OpenSentry Command Center.
Discovers OpenSentry camera nodes on the local network.
"""
import socket
import time
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from ..models.camera import CAMERAS, cameras_lock, camera_streams
from ..config import Config
from .camera import CameraStream

# mDNS browser instances
_zeroconf = None
_browser = None
_listener = None


class OpenSentryServiceListener(ServiceListener):
    """Listener for OpenSentry node mDNS announcements"""
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a new OpenSentry node is discovered"""
        print(f"[mDNS] Discovered service: {name}")
        info = zc.get_service_info(type_, name)
        
        if info:
            self._register_node(name, info)
        else:
            print(f"[mDNS] Failed to resolve service: {name}")
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when an OpenSentry node goes offline"""
        print(f"[mDNS] Service removed: {name}")
        self._unregister_node(name)
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is updated"""
        info = zc.get_service_info(type_, name)
        if info:
            self._update_node_status(name, info)
    
    def _extract_properties(self, info) -> dict:
        """Extract properties from mDNS TXT records"""
        properties = {}
        if info.properties:
            for key, value in info.properties.items():
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value)
                properties[key_str] = value_str
        return properties
    
    def _update_node_status(self, name: str, info) -> None:
        """Update status for an existing node without full re-registration"""
        properties = self._extract_properties(info)
        camera_id = properties.get('camera_id', name.split('.')[0])
        new_status = properties.get('status', 'unknown')
        
        with cameras_lock:
            if camera_id in CAMERAS:
                if CAMERAS[camera_id].get('status') != new_status:
                    print(f"[mDNS] {camera_id} status: {new_status}")
                CAMERAS[camera_id]['status'] = new_status
                CAMERAS[camera_id]['last_seen'] = time.time()
            else:
                self._register_node(name, info)
    
    def _register_node(self, name: str, info) -> None:
        """Register a discovered node as a camera"""
        properties = self._extract_properties(info)
        
        ip_address = None
        if info.addresses:
            ip_address = socket.inet_ntoa(info.addresses[0])
        
        camera_id = properties.get('camera_id', name.split('.')[0])
        camera_name = properties.get('name', f"Camera {camera_id}")
        
        rtsp_url = properties.get('rtsp_url', None)
        if rtsp_url:
            rtsp_url = rtsp_url.replace('localhost', ip_address).replace('127.0.0.1', ip_address)
        else:
            rtsp_port = properties.get('rtsp_port', '8554')
            rtsp_path = properties.get('rtsp_path', camera_id)
            if not rtsp_path.startswith('/'):
                rtsp_path = '/' + rtsp_path
            rtsp_url = f"rtsp://{ip_address}:{rtsp_port}{rtsp_path}"
        
        initial_status = properties.get('status', 'discovered')
        
        print(f"[mDNS] Registering camera: {camera_id}", flush=True)
        print(f"       Name: {camera_name}", flush=True)
        print(f"       IP: {ip_address}:{info.port}", flush=True)
        print(f"       RTSP: {rtsp_url}", flush=True)
        print(f"       Status: {initial_status}", flush=True)
        
        with cameras_lock:
            CAMERAS[camera_id] = {
                'name': camera_name,
                'url': rtsp_url,
                'ip': ip_address,
                'port': info.port,
                'status': initial_status,
                'last_seen': time.time(),
                'mdns_name': name,
                'discovered_via': 'mdns'
            }
            
            if camera_id not in camera_streams:
                stream = CameraStream(camera_id, rtsp_url)
                camera_streams[camera_id] = stream
                stream.start()
            else:
                if camera_streams[camera_id].original_url != rtsp_url:
                    camera_streams[camera_id].stop()
                    stream = CameraStream(camera_id, rtsp_url)
                    camera_streams[camera_id] = stream
                    stream.start()
    
    def _unregister_node(self, name: str) -> None:
        """Unregister a node when it goes offline"""
        with cameras_lock:
            camera_id_to_remove = None
            for camera_id, camera_info in CAMERAS.items():
                if camera_info.get('mdns_name') == name:
                    camera_id_to_remove = camera_id
                    break
            
            if camera_id_to_remove:
                if camera_id_to_remove in camera_streams:
                    camera_streams[camera_id_to_remove].stop()
                    del camera_streams[camera_id_to_remove]
                
                CAMERAS[camera_id_to_remove]['status'] = 'offline'
                print(f"[mDNS] Camera {camera_id_to_remove} marked offline")


def start_discovery():
    """Start mDNS service discovery for OpenSentry nodes"""
    global _zeroconf, _browser, _listener
    
    print(f"[mDNS] Starting discovery for {Config.MDNS_SERVICE_TYPE}")
    
    _zeroconf = Zeroconf()
    _listener = OpenSentryServiceListener()
    _browser = ServiceBrowser(_zeroconf, Config.MDNS_SERVICE_TYPE, _listener)
    
    print("[mDNS] Discovery started, listening for OpenSentry nodes...", flush=True)


def stop_discovery():
    """Stop mDNS discovery"""
    global _zeroconf
    if _zeroconf:
        _zeroconf.close()
        print("[mDNS] Discovery stopped")
