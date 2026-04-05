import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Clerk Authentication (required)
    CLERK_SECRET_KEY: str = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    CLERK_WEBHOOK_SECRET: str = os.getenv("CLERK_WEBHOOK_SECRET", "")
    CLERK_JWKS_URL: str = os.getenv("CLERK_JWKS_URL", "")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./opensentry.db")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    OPENSENTRY_SECRET: str = os.getenv("OPENSENTRY_SECRET", "")

    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT", "30"))

    AWS_ENDPOINT_URL_S3: str = os.getenv("AWS_ENDPOINT_URL_S3", "")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "auto")
    TIGRIS_BUCKET_NAME: str = os.getenv("BUCKET_NAME", "")

    STREAM_URL_EXPIRY_SECONDS: int = int(os.getenv("STREAM_URL_EXPIRY_SECONDS", "300"))
    SEGMENT_URL_EXPIRY_SECONDS: int = int(os.getenv("SEGMENT_URL_EXPIRY_SECONDS", "300"))
    UPLOAD_URL_EXPIRY_SECONDS: int = int(os.getenv("UPLOAD_URL_EXPIRY_SECONDS", "300"))
    UPLOAD_TIMEOUT_MINUTES: int = int(os.getenv("UPLOAD_TIMEOUT_MINUTES", "10"))
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "7"))
    SEGMENT_RETENTION_COUNT: int = int(os.getenv("SEGMENT_RETENTION_COUNT", "60"))
    CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "20"))

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)


settings = Config()
