from typing import Optional, List
from pydantic import BaseModel, Field


class CameraGroupCreate(BaseModel):
    name: str = Field(..., max_length=100)
    color: Optional[str] = Field("#22c55e", max_length=20)
    icon: Optional[str] = Field("📁", max_length=10)


class RecordingSettings(BaseModel):
    scheduled_recording: bool = False
    scheduled_start: str = Field("06:00", max_length=5)
    scheduled_end: str = Field("17:00", max_length=5)
    continuous_24_7: bool = False


class CameraReport(BaseModel):
    camera_id: Optional[str] = Field(None, max_length=150)
    device_path: Optional[str] = Field(None, max_length=255)
    name: Optional[str] = Field(None, max_length=100)
    node_type: Optional[str] = Field("usb", max_length=20)
    capabilities: Optional[List[str]] = []
    width: Optional[int] = Field(1280, ge=1, le=7680)
    height: Optional[int] = Field(720, ge=1, le=4320)


class NodeRegister(BaseModel):
    node_id: str = Field(..., max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    hostname: Optional[str] = Field(None, max_length=255)
    local_ip: Optional[str] = Field(None, max_length=45)
    http_port: Optional[int] = Field(8080, ge=1, le=65535)
    cameras: Optional[List[CameraReport]] = []
    video_codec: Optional[str] = Field(None, max_length=50)
    audio_codec: Optional[str] = Field(None, max_length=50)


class CameraStatus(BaseModel):
    camera_id: str = Field(..., max_length=150)
    status: str = Field(..., max_length=20)


class NodeHeartbeat(BaseModel):
    node_id: str = Field(..., max_length=50)
    local_ip: Optional[str] = Field(None, max_length=45)
    cameras: Optional[List[CameraStatus]] = []


class NodeCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
