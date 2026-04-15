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

    # Sentry error tracking.  Leave blank for local dev/tests — the init
    # module no-ops gracefully and never phones home.  In production set
    # this to your project DSN from sentry.io; environment/release are
    # inferred from Fly env vars (FLY_APP_NAME, FLY_MACHINE_VERSION).
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    # Trace sample rate — 0.1 keeps us inside Sentry's free-tier event
    # budget at expected volumes.  Bump when you need finer perf insight.
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    # Segments kept in memory per camera for the live proxy cache.
    # CloudNode ships with 1-second segments by default, so 15 = ~15s of buffer —
    # enough for HLS to start at the live edge and recover from one short stall.
    SEGMENT_CACHE_MAX_PER_CAMERA: int = int(os.getenv("SEGMENT_CACHE_MAX_PER_CAMERA", "15"))
    # Max size of a single pushed segment (safety valve).
    SEGMENT_PUSH_MAX_BYTES: int = int(os.getenv("SEGMENT_PUSH_MAX_BYTES", str(2 * 1024 * 1024)))
    # How often (in playlist updates) to run cache eviction.
    CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "20"))

    # CloudNode version compatibility.
    #
    # MIN_SUPPORTED_NODE_VERSION — register/heartbeat from a CloudNode older
    # than this is rejected with HTTP 426 Upgrade Required.  Bump only when
    # we ship a wire-protocol break that genuinely cannot interop with the
    # old client.  A missing version field (Node version unknown / 0.0.0) is
    # always tolerated for now so very old CloudNodes that pre-date version
    # reporting can still register and be told to upgrade.
    #
    # LATEST_NODE_VERSION — what the CloudNode installer would download today.
    # If a node reports a version older than this we still accept it, but the
    # response includes an `update_available` hint so the dashboard can nudge
    # the operator.  Update this on every CloudNode release.
    MIN_SUPPORTED_NODE_VERSION: str = os.getenv("MIN_SUPPORTED_NODE_VERSION", "0.1.0")
    # Bumped to 0.1.7 on 2026-04-15 alongside the Linux/Pi polish release
    # (segment retry numeric-status classifier + USB enumeration wait).
    # 0.1.6 nodes still work but the retry bug means they can drop
    # segments during Fly cold-starts — operators should update.  Keep
    # this in lockstep with the newest GitHub release of
    # opensentry-cloud-node.
    LATEST_NODE_VERSION: str = os.getenv("LATEST_NODE_VERSION", "0.1.7")

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)


settings = Config()
