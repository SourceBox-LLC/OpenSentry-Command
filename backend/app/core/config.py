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

    # Segments kept in memory per camera for the live proxy cache.
    # With 2-second segments, 15 = ~30 seconds — enough for HLS playback buffer.
    SEGMENT_CACHE_MAX_PER_CAMERA: int = int(os.getenv("SEGMENT_CACHE_MAX_PER_CAMERA", "15"))
    # Max size of a single pushed segment (safety valve).
    SEGMENT_PUSH_MAX_BYTES: int = int(os.getenv("SEGMENT_PUSH_MAX_BYTES", str(2 * 1024 * 1024)))
    # How often (in playlist updates) to run cache eviction.
    CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "20"))

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)


settings = Config()
