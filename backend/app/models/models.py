import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    Boolean,
    Float,
    ForeignKey,
    LargeBinary,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("camera_nodes.id"), nullable=True)
    name = Column(String(100), nullable=False)
    node_type = Column(String(20), default="unknown")
    capabilities = Column(String(500), default="streaming")
    group_id = Column(Integer, ForeignKey("camera_groups.id"), nullable=True)
    last_seen = Column(DateTime)
    status = Column(String(20), default="offline")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Codec detection fields
    video_codec = Column(String(50), nullable=True)  # e.g., "avc1.42001E"
    audio_codec = Column(String(50), nullable=True)  # e.g., "mp4a.40.2"
    codec_detected_at = Column(DateTime, nullable=True)

    media = relationship("Media", back_populates="camera", cascade="all, delete-orphan")
    group = relationship("CameraGroup", back_populates="cameras")
    node = relationship("CameraNode", back_populates="cameras")

    def to_dict(self):
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "node_type": self.node_type,
            "capabilities": self.capabilities.split(",") if self.capabilities else [],
            "group": self.group.name if self.group else None,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class CameraGroup(Base):
    __tablename__ = "camera_groups"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(7), default="#22c55e")
    icon = Column(String(10), default="📁")
    created_at = Column(DateTime, default=datetime.utcnow)

    cameras = relationship("Camera", back_populates="group")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "camera_count": len(self.cameras) if self.cameras else 0,
        }


class Media(Base):
    __tablename__ = "media"

    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True)
    org_id = Column(String(100), nullable=False, index=True)
    media_type = Column(String(20), nullable=False)
    filename = Column(String(255), unique=True, nullable=False, index=True)
    mimetype = Column(String(50), default="application/octet-stream")
    data = Column(LargeBinary, nullable=False)
    size = Column(Integer, default=0)
    duration = Column(Float, nullable=True)
    thumbnail = Column(LargeBinary, nullable=True)
    tags = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    camera = relationship("Camera", back_populates="media")

    def to_dict(self):
        return {
            "id": self.id,
            "camera_id": self.camera.camera_id if self.camera else None,
            "type": self.media_type,
            "filename": self.filename,
            "size": self.size,
            "duration": self.duration,
            "tags": self.tags.split(",") if self.tags else [],
            "created": self.created_at.timestamp(),
            "url": f"/api/{'snapshots' if self.media_type == 'snapshot' else 'recordings'}/{self.id}",
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    detection_type = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    region_x = Column(Integer, nullable=True)
    region_y = Column(Integer, nullable=True)
    region_width = Column(Integer, nullable=True)
    region_height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    processed = Column(Boolean, default=False)

    def to_dict(self):
        region = None
        if self.region_x is not None:
            region = {
                "x": self.region_x,
                "y": self.region_y,
                "width": self.region_width,
                "height": self.region_height,
            }
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "type": self.detection_type,
            "confidence": self.confidence,
            "region": region,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "processed": self.processed,
        }


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(db, org_id: str, key: str, default: str = None) -> str:
        setting = db.query(Setting).filter_by(org_id=org_id, key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(db, org_id: str, key: str, value: str):
        setting = db.query(Setting).filter_by(org_id=org_id, key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(org_id=org_id, key=key, value=value)
            db.add(setting)
        db.commit()
        return setting


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event = Column(String(50), nullable=False, index=True)
    ip_address = Column(String(45))
    username = Column(String(80))
    user_id = Column(String(100))
    details = Column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "ip": self.ip_address,
            "username": self.username,
            "details": self.details,
        }


class CameraNode(Base):
    __tablename__ = "camera_nodes"

    id = Column(Integer, primary_key=True)
    node_id = Column(String(100), unique=True, nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    api_key_hash = Column(String(128), nullable=False)
    name = Column(String(100), nullable=False)
    hostname = Column(String(100))
    local_ip = Column(String(45))
    http_port = Column(Integer, default=8080)
    status = Column(String(20), default="offline")
    last_seen = Column(DateTime)
    key_rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    upload_count = Column(Integer, default=0)
    video_codec = Column(String(50), nullable=True)
    audio_codec = Column(String(50), nullable=True)
    codec_detected_at = Column(DateTime, nullable=True)

    cameras = relationship(
        "Camera", back_populates="node", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "name": self.name,
            "hostname": self.hostname,
            "local_ip": self.local_ip,
            "http_port": self.http_port,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "key_rotated_at": self.key_rotated_at.isoformat()
            if self.key_rotated_at
            else None,
            "camera_count": len(self.cameras) if self.cameras else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
        }


class StreamAccessLog(Base):
    __tablename__ = "stream_access_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    node_id = Column(String(100), nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    accessed_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "camera_id": self.camera_id,
            "node_id": self.node_id,
            "ip_address": self.ip_address,
            "accessed_at": self.accessed_at.isoformat(),
        }


class PendingUpload(Base):
    __tablename__ = "pending_uploads"

    id = Column(Integer, primary_key=True)
    upload_id = Column(String(100), unique=True, nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    node_id = Column(String(100), nullable=False)
    s3_key = Column(String(500), nullable=False)
    expected_checksum = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    completed = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "upload_id": self.upload_id,
            "camera_id": self.camera_id,
            "org_id": self.org_id,
            "s3_key": self.s3_key,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "completed": self.completed,
        }
