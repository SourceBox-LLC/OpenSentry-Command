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
    SENTRY_TRACES_SAMPLE_RATE: float = float(
        os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
    )

    # Segments kept in memory per camera for the live proxy cache.
    # CloudNode ships with 1-second segments by default, so 60 = ~60s of buffer —
    # enough for HLS to recover from network stalls without falling off the cache edge.
    SEGMENT_CACHE_MAX_PER_CAMERA: int = int(
        os.getenv("SEGMENT_CACHE_MAX_PER_CAMERA", "60")
    )
    # Hard byte ceiling on the SUM of all camera segment caches.
    # SEGMENT_CACHE_MAX_PER_CAMERA bounds per-camera; this bounds the
    # total.  Without it, an unexpected surge in active cameras (e.g.
    # an MSP onboarding 200 nodes in one day) can OOM the Fly machine
    # before the per-camera limits would even rotate.  When exceeded,
    # the global eviction in hls.py drops the oldest segments across
    # ALL cameras until the total is back under the cap — preserves
    # the live-edge for active cameras at the cost of dropping the
    # tail of less-active ones.  Default 2 GiB chosen to leave the
    # 1 GiB Fly machine headroom for the rest of the app on a 4 GiB
    # box (typical production size).  Bump when you scale the box.
    SEGMENT_CACHE_MAX_TOTAL_BYTES: int = int(
        os.getenv("SEGMENT_CACHE_MAX_TOTAL_BYTES", str(2 * 1024 * 1024 * 1024))
    )
    # Max size of a single pushed segment (safety valve).  Enforced
    # via Content-Length BEFORE the body is read, plus a post-read
    # check for chunked transfers.
    SEGMENT_PUSH_MAX_BYTES: int = int(
        os.getenv("SEGMENT_PUSH_MAX_BYTES", str(2 * 1024 * 1024))
    )
    # Max size of a single pushed HLS playlist (m3u8).  A real
    # playlist is typically 1-2 KB; 64 KB leaves comfortable headroom
    # for unusually long segment lists or paranoid future formats
    # without letting an attacker burn unbounded memory pushing
    # garbage into /playlist.
    PLAYLIST_PUSH_MAX_BYTES: int = int(
        os.getenv("PLAYLIST_PUSH_MAX_BYTES", str(64 * 1024))
    )
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
    # LATEST_NODE_VERSION — disaster fallback for the latest-version
    # lookup.  As of 2026-04-28 the runtime resolves this dynamically
    # by polling GitHub /releases/latest in app.core.release_cache, so
    # this constant is only read on cold-boot before the first refresh
    # tick lands AND when GitHub is unreachable for the full TTL.  In
    # practice that means it almost never gets read — but it MUST be
    # set to a real version to keep ``update_available`` sensible
    # during a sustained GitHub outage.  The value here is the floor,
    # not the ceiling: the cache will surface a newer version as soon
    # as one ships, with no Command Center deploy required.
    MIN_SUPPORTED_NODE_VERSION: str = os.getenv("MIN_SUPPORTED_NODE_VERSION", "0.1.0")
    LATEST_NODE_VERSION: str = os.getenv("LATEST_NODE_VERSION", "0.1.26")

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)


settings = Config()
