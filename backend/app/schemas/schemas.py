from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.models import Alert, Camera, CameraGroup, Media


class CameraCreate(BaseModel):
    camera_id: str
    name: str
    node_type: Optional[str] = "unknown"
    capabilities: Optional[List[str]] = []
    notes: Optional[str] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    group_id: Optional[int] = None


class CameraResponse(BaseModel):
    camera_id: str
    name: str
    node_type: str
    capabilities: List[str]
    group: Optional[str] = None
    status: str
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True


class CameraGroupCreate(BaseModel):
    name: str
    color: Optional[str] = "#22c55e"
    icon: Optional[str] = "📁"


class CameraGroupResponse(BaseModel):
    id: int
    name: str
    color: str
    icon: str
    camera_count: int

    class Config:
        from_attributes = True


class MediaResponse(BaseModel):
    id: int
    camera_id: Optional[str] = None
    type: str
    filename: str
    size: int
    duration: Optional[float] = None
    tags: List[str]
    created: float
    url: str

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: int
    camera_id: str
    type: str
    confidence: Optional[float] = None
    region: Optional[dict] = None
    timestamp: Optional[str] = None
    processed: bool

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    key: str
    value: str


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


class CameraCommand(BaseModel):
    command: str


class AlertCreate(BaseModel):
    camera_id: str
    detection_type: str
    confidence: Optional[float] = None
    region_x: Optional[int] = None
    region_y: Optional[int] = None
    region_width: Optional[int] = None
    region_height: Optional[int] = None


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


class NodeHeartbeat(BaseModel):
    node_id: str
    local_ip: Optional[str] = None
    cameras: Optional[List[dict]] = []


class NodeCreate(BaseModel):
    name: Optional[str] = None
