"""
Configuration classes for OpenSentry Command Center.
"""
import os
import hashlib
from datetime import timedelta


class Config:
    """Base configuration class"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Session timeout (minutes)
    SESSION_TIMEOUT_MINUTES = int(os.environ.get('SESSION_TIMEOUT', '30'))
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    SESSION_REFRESH_EACH_REQUEST = True
    
    # Authentication
    OPENSENTRY_USERNAME = os.environ.get('OPENSENTRY_USERNAME', 'admin')
    OPENSENTRY_PASSWORD = os.environ.get('OPENSENTRY_PASSWORD', 'opensentry')
    
    # Rate limiting
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION = 300  # 5 minutes
    ATTEMPT_WINDOW = 900    # 15 minutes
    
    # MQTT (TLS on port 8883)
    MQTT_BROKER = os.environ.get('MQTT_BROKER', 'localhost')
    MQTT_PORT = int(os.environ.get('MQTT_PORT', '8883'))
    MQTT_USE_TLS = os.environ.get('MQTT_USE_TLS', 'true').lower() == 'true'
    MQTT_CLIENT_ID = 'opensentry_command_center'
    MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'opensentry')
    MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', 'opensentry')
    
    # RTSP
    RTSP_USERNAME = os.environ.get('RTSP_USERNAME', 'opensentry')
    RTSP_PASSWORD = os.environ.get('RTSP_PASSWORD', 'opensentry')
    
    # Single secret for credential derivation
    OPENSENTRY_SECRET = os.environ.get('OPENSENTRY_SECRET', '')
    
    # mDNS
    MDNS_SERVICE_TYPE = '_opensentry._tcp.local.'
    
    @classmethod
    def init_secret_key(cls):
        """Generate secret key if not provided"""
        if not cls.SECRET_KEY:
            cls.SECRET_KEY = hashlib.sha256(
                f"opensentry-{cls.OPENSENTRY_USERNAME}-{cls.OPENSENTRY_PASSWORD}".encode()
            ).hexdigest()
        return cls.SECRET_KEY


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
