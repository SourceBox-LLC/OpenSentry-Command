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

    # ── Email notifications (Resend) ─────────────────────────────────
    # Resend transactional email integration for operator-critical
    # notifications (camera offline, node offline, disk critical, new
    # incident).  See docs/legal/SUB_PROCESSORS.md for the disclosure
    # and app/core/email_worker.py for the send path.
    #
    # EMAIL_ENABLED is the global kill-switch — code can ship with it
    # off (the default), then operator flips it on once DNS propagates
    # and a smoke test passes.  Worker still runs when off, but the
    # transport short-circuits with a logged "would have sent" line so
    # local dev doesn't burn the free-tier daily limit.
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_WEBHOOK_SECRET: str = os.getenv("RESEND_WEBHOOK_SECRET", "")
    EMAIL_FROM_ADDRESS: str = os.getenv(
        "EMAIL_FROM_ADDRESS", "notifications@sourceboxsentry.com"
    )
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "SourceBox Sentry")
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    # Worker tunables.  5s tick keeps median time-to-deliver under 10s
    # without hammering SQLite; 20-row batch keeps a single tick under
    # Resend's default rate limit (10 req/sec on new accounts).
    EMAIL_WORKER_INTERVAL_SECONDS: int = int(
        os.getenv("EMAIL_WORKER_INTERVAL_SECONDS", "5")
    )
    EMAIL_WORKER_BATCH_SIZE: int = int(
        os.getenv("EMAIL_WORKER_BATCH_SIZE", "20")
    )
    # Max attempts before a row gets marked 'failed' permanently and
    # the worker stops retrying.  3 covers transient Resend 5xx /
    # network blips without piling up infinite zombie rows when their
    # API has a real outage.
    EMAIL_MAX_ATTEMPTS: int = int(os.getenv("EMAIL_MAX_ATTEMPTS", "3"))

    @classmethod
    def is_clerk_configured(cls) -> bool:
        return bool(cls.CLERK_SECRET_KEY and cls.CLERK_PUBLISHABLE_KEY)

    @classmethod
    def is_email_configured(cls) -> bool:
        """True iff the Resend transport has the credentials it needs.
        EMAIL_ENABLED is the operator switch; this checks the wiring.
        Health endpoint reports both separately so an operator can tell
        'I forgot to set the secret' from 'I left the kill-switch off'.
        """
        return bool(cls.RESEND_API_KEY and cls.EMAIL_FROM_ADDRESS)


settings = Config()
