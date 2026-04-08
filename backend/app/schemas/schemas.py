from typing import Optional, List
from pydantic import BaseModel


class CameraGroupCreate(BaseModel):
    name: str
    color: Optional[str] = "#22c55e"
    icon: Optional[str] = "📁"


class RecordingSettings(BaseModel):
    motion_recording: bool = False
    face_recording: bool = False
    object_recording: bool = False
    post_buffer: int = 5
    scheduled_recording: bool = False
    scheduled_start: str = "06:00"
    scheduled_end: str = "17:00"
    continuous_24_7: bool = False


class NotificationSettings(BaseModel):
    motion_notifications: bool = True
    face_notifications: bool = True
    object_notifications: bool = True
    toast_notifications: bool = True


class CameraReport(BaseModel):
    camera_id: Optional[str] = None  # Generated if not provided
    device_path: Optional[str] = None  # For CloudNode: /dev/video0, etc.
    name: Optional[str] = None
    node_type: Optional[str] = "usb"
    capabilities: Optional[List[str]] = []
    width: Optional[int] = 1280
    height: Optional[int] = 720


class NodeRegister(BaseModel):
    node_id: str
    name: Optional[str] = None
    hostname: Optional[str] = None
    local_ip: Optional[str] = None
    http_port: Optional[int] = 8080
    cameras: Optional[List[CameraReport]] = []
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None


class CameraStatus(BaseModel):
    camera_id: str
    status: str


class NodeHeartbeat(BaseModel):
    node_id: str
    local_ip: Optional[str] = None
    cameras: Optional[List[CameraStatus]] = []


class NodeCreate(BaseModel):
    name: Optional[str] = None
