"""
SQLAlchemy database models for OpenSentry Command Center.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User account for authentication"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="viewer")  # admin, viewer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user has admin role"""
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username}>"


class CameraGroup(db.Model):
    """Camera grouping/organization"""

    __tablename__ = "camera_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    color = db.Column(db.String(7), default="#22c55e")  # Hex color
    icon = db.Column(db.String(10), default="📁")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cameras = db.relationship("Camera", backref="group", lazy="dynamic")

    def __repr__(self):
        return f"<CameraGroup {self.name}>"


class Camera(db.Model):
    """Persistent camera metadata"""

    __tablename__ = "cameras"

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    node_type = db.Column(db.String(20), default="unknown")  # basic, motion, unknown
    capabilities = db.Column(
        db.String(500), default="streaming"
    )  # comma-separated list
    group_id = db.Column(db.Integer, db.ForeignKey("camera_groups.id"), nullable=True)
    rtsp_url = db.Column(db.String(500))
    mqtt_port = db.Column(db.Integer, default=8883)
    last_seen = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="offline")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    media = db.relationship(
        "Media", backref="camera", lazy="dynamic", cascade="all, delete-orphan"
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "node_type": self.node_type,
            "capabilities": self.capabilities.split(",") if self.capabilities else [],
            "group": self.group.name if self.group else None,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "rtsp_url": self.rtsp_url,
            "mqtt_port": self.mqtt_port,
        }

    def __repr__(self):
        return f"<Camera {self.camera_id}>"


class Media(db.Model):
    """Media storage with binary blob data"""

    __tablename__ = "media"

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("cameras.id"), nullable=True)
    media_type = db.Column(db.String(20), nullable=False)  # snapshot, recording
    filename = db.Column(db.String(255), unique=True, nullable=False, index=True)
    mimetype = db.Column(db.String(50), default="application/octet-stream")
    data = db.Column(db.LargeBinary, nullable=False)  # Binary blob storage
    size = db.Column(db.Integer, default=0)  # bytes
    duration = db.Column(db.Float, nullable=True)  # seconds (for recordings)
    thumbnail = db.Column(db.LargeBinary, nullable=True)  # Thumbnail blob for videos
    tags = db.Column(db.String(500), default="")  # comma-separated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary for API responses (excludes binary data)"""
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

    def __repr__(self):
        return f"<Media {self.filename}>"


class AuditLog(db.Model):
    """Security audit trail"""

    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    event = db.Column(db.String(50), nullable=False, index=True)
    ip_address = db.Column(db.String(45))  # IPv6 max length
    username = db.Column(db.String(80))
    details = db.Column(db.Text)

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "ip": self.ip_address,
            "username": self.username,
            "details": self.details,
        }

    def __repr__(self):
        return f"<AuditLog {self.event} {self.timestamp}>"


class Setting(db.Model):
    """Application settings"""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @staticmethod
    def get(key, default=None):
        """Get a setting value"""
        setting = Setting.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        """Set a setting value"""
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return setting

    def __repr__(self):
        return f"<Setting {self.key}>"


class RateLimit(db.Model):
    """Persist rate limiting data to survive restarts"""

    __tablename__ = "rate_limits"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    failed_attempts = db.Column(db.Integer, default=0)
    first_attempt = db.Column(db.DateTime, default=datetime.utcnow)
    last_attempt = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    locked_until = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def get_attempts(ip_address, window_seconds=900):
        """Get failed attempts within time window"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)

        record = RateLimit.query.filter_by(ip_address=ip_address).first()
        if not record:
            return [], None

        # Check if record is still valid
        if record.first_attempt < cutoff:
            # Clean up old record
            db.session.delete(record)
            db.session.commit()
            return [], None

        return record, record.locked_until

    @staticmethod
    def record_failed_attempt(
        ip_address, window_seconds=900, max_attempts=5, lockout_seconds=300
    ):
        """Record a failed login attempt"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)

        record = RateLimit.query.filter_by(ip_address=ip_address).first()
        if not record:
            record = RateLimit(
                ip_address=ip_address,
                failed_attempts=0,
                first_attempt=datetime.utcnow(),
            )
            db.session.add(record)

        record.failed_attempts += 1
        record.last_attempt = datetime.utcnow()

        # Check if should lock out
        if record.failed_attempts >= max_attempts:
            record.locked_until = datetime.utcnow() + timedelta(seconds=lockout_seconds)

        db.session.commit()
        return record.failed_attempts, record.locked_until

    @staticmethod
    def clear_attempts(ip_address):
        """Clear failed attempts after successful login"""
        record = RateLimit.query.filter_by(ip_address=ip_address).first()
        if record:
            db.session.delete(record)
            db.session.commit()

    @staticmethod
    def is_locked(ip_address):
        """Check if IP is currently locked out"""
        record = RateLimit.query.filter_by(ip_address=ip_address).first()
        if not record or not record.locked_until:
            return False, 0

        if record.locked_until > datetime.utcnow():
            remaining = (record.locked_until - datetime.utcnow()).total_seconds()
            return True, int(remaining)

        return False, 0

    def __repr__(self):
        return f"<RateLimit {self.ip_address}>"


class Alert(db.Model):
    """Detection alerts stored for historical querying"""

    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.String(100), nullable=False, index=True)
    detection_type = db.Column(db.String(20), nullable=False)  # motion, face, object
    confidence = db.Column(db.Float, nullable=True)  # Detection confidence 0-100
    thumbnail_path = db.Column(db.String(500), nullable=True)

    # Motion region/bounding box data
    region_x = db.Column(db.Integer, nullable=True)
    region_y = db.Column(db.Integer, nullable=True)
    region_width = db.Column(db.Integer, nullable=True)
    region_height = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    processed = db.Column(db.Boolean, default=False)  # For acknowledgment

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
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

    def __repr__(self):
        return f"<Alert {self.detection_type} from {self.camera_id}>"


def init_db(app):
    """Initialize database and create tables"""
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # Create default admin user if no users exist
        if User.query.count() == 0:
            from ..config import Config

            admin = User(username=Config.OPENSENTRY_USERNAME or "admin", role="admin")
            admin.set_password(Config.OPENSENTRY_PASSWORD or "opensentry")
            db.session.add(admin)
            db.session.commit()
            print(f"[Database] Created default admin user: {admin.username}")

        # Create default camera group if none exist
        if CameraGroup.query.count() == 0:
            default_group = CameraGroup(name="Default", icon="🏠")
            db.session.add(default_group)
            db.session.commit()
            print("[Database] Created default camera group")

        # Add region columns to alerts table if they don't exist (migration)
        try:
            result = db.session.execute(db.text("SELECT region_x FROM alerts LIMIT 1"))
            result.fetchone()
            # Column exists
        except Exception:
            # Column doesn't exist, add them
            print("[Database] Adding region columns to alerts table...")
            try:
                db.session.execute(
                    db.text("""
                    ALTER TABLE alerts ADD COLUMN region_x INTEGER
                """)
                )
                db.session.execute(
                    db.text("""
                    ALTER TABLE alerts ADD COLUMN region_y INTEGER
                """)
                )
                db.session.execute(
                    db.text("""
                    ALTER TABLE alerts ADD COLUMN region_width INTEGER
                """)
                )
                db.session.execute(
                    db.text("""
                    ALTER TABLE alerts ADD COLUMN region_height INTEGER
                """)
                )
                db.session.commit()
                print("[Database] Added region columns to alerts table")
            except Exception as e:
                print(f"[Database] Migration note: {e}")

        print("[Database] Initialized successfully")
