import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Clerk Authentication (required)
    CLERK_SECRET_KEY: str = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    CLERK_WEBHOOK_SECRET: str = os.getenv("CLERK_WEBHOOK_SECRET", "")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./opensentry.db")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Rate-limiter shared storage.  In production set REDIS_URL to a
    # managed instance (Upstash on Fly, etc.) so limits hold across VMs —
    # without it, each VM keeps its own in-memory counters and an
    # attacker round-robining across instances gets N× the stated rate.
    # In dev / tests the empty default is fine; slowapi falls back to
    # in-memory storage and logs a one-shot warning at startup.
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # Segments kept in memory per camera for the live proxy cache.
    # CloudNode ships with 1-second segments by default, so 15 = ~15s of buffer —
    # enough for HLS to start at the live edge and recover from one short stall.
    SEGMENT_CACHE_MAX_PER_CAMERA: int = int(os.getenv("SEGMENT_CACHE_MAX_PER_CAMERA", "15"))
    # Max size of a single pushed segment (safety valve).
    SEGMENT_PUSH_MAX_BYTES: int = int(os.getenv("SEGMENT_PUSH_MAX_BYTES", str(2 * 1024 * 1024)))
    # How often (in playlist updates) to run cache eviction.
    CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "20"))

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)


settings = Config()
