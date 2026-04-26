import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Process start markers for ``/api/health/detailed``. Captured at module
# import (i.e. uvicorn cold-start) so uptime is real wall + monotonic
# time, not "ms since the request handler ran". Module-level constants
# are fine — there's only ever one process per Fly machine.
_STARTED_AT_WALL = datetime.now(tz=timezone.utc)
_STARTED_AT_MONO = time.monotonic()
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.limiter import limiter
from app.core.migrations import sync_schema, sanitize_existing_codecs, drop_orphan_tables
from app.core.sentry import init_sentry
from app.api import cameras, webhooks, nodes, audit, hls, ws, install, mcp_keys, mcp_activity, incidents, motion, notifications
from app.mcp.server import mcp
# Import models so every table registers on Base.metadata before create_all/sync_schema.
from app.models import models  # noqa: F401

logger = logging.getLogger(__name__)

# Initialise Sentry as early as possible — before we register routes — so
# any exception raised during app construction is still captured. No-ops
# cleanly when SENTRY_DSN is unset (local dev, tests).
init_sentry(
    dsn=settings.SENTRY_DSN or None,
    traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
)

Base.metadata.create_all(bind=engine)
# Patch in any columns that were added to existing models after the table was first
# created. See app/core/migrations.py for the "why" — this is our stand-in for Alembic.
sync_schema(engine, Base.metadata)
# Drop tables for models we've retired (sync_schema doesn't touch these).
# Currently sweeps `webhook_endpoints` left behind by the d4dd2db revert.
drop_orphan_tables(engine)
# One-time data sweep — rescue any rows still holding the garbage
# `avc1.*e00a`-class codec string from the pre-v0.1.6 CloudNode bug.
# Idempotent; post-fix boots match zero rows.
sanitize_existing_codecs(engine)

# Build the MCP ASGI app — path="/" because the mount prefix handles /mcp
mcp_app = mcp.http_app(path="/", stateless_http=True, json_response=True)


# ── Background-loop tunables ──────────────────────────────────────
# These are defined *here* (above the functions that reference them)
# so the f-string in ``lifespan`` doesn't depend on the rest of the
# module having loaded first. lifespan is invoked by uvicorn during
# app startup, after the module is fully imported, so the old layout
# worked — but it was fragile to any refactor that called the
# function during import. Putting the constants up top makes the
# dependency direction obvious.

# Fallback retention for orgs whose plan can't be resolved (Clerk lookup
# failed AND no cached Setting). The per-org tiered retention —
# 30d / 90d / 365d for Free / Pro / Pro Plus — is sourced from
# ``app.core.plans.PLAN_LIMITS[plan]["log_retention_days"]`` and applied
# in ``_log_cleanup_loop`` below. This env var only matters when plan
# resolution breaks entirely; we keep a 90-day default so a transient
# Clerk outage doesn't silently wipe a paid customer's logs.
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "90"))
LOG_CLEANUP_INTERVAL_HOURS = 24  # Run once per day
# Cameras offline for longer than this get their in-memory caches freed.
# HLS segments are live-only fragments — useless once streaming stops.
INACTIVE_CAMERA_CLEANUP_HOURS = int(os.getenv("INACTIVE_CAMERA_CLEANUP_HOURS", "24"))

# How often to sweep for stale "online" entities and flip them to offline.
# Needs to be shorter than the heartbeat-miss threshold (90s) for
# timely notifications but longer than a few seconds to keep DB load low.
OFFLINE_SWEEP_INTERVAL_SECONDS = int(os.getenv("OFFLINE_SWEEP_INTERVAL_SECONDS", "30"))
# If a node/camera hasn't heart-beat in this many seconds, the sweep
# marks it offline.  Matches the 90s threshold used by the model's
# ``effective_status`` property so the UI and DB agree.
OFFLINE_HEARTBEAT_TIMEOUT_SECONDS = 90


@asynccontextmanager
async def lifespan(app):
    """Application lifespan: startup and shutdown hooks."""
    cleanup_task = asyncio.create_task(_log_cleanup_loop())
    offline_sweep_task = asyncio.create_task(_offline_sweep_loop())
    viewer_usage_task = asyncio.create_task(_viewer_usage_flush_loop())
    print(f"[App] SourceBox Sentry Command Center started (log retention: {LOG_RETENTION_DAYS}d)")
    async with mcp_app.lifespan(app):
        yield
    cleanup_task.cancel()
    offline_sweep_task.cancel()
    viewer_usage_task.cancel()
    print("[System] Shutdown complete")


app = FastAPI(
    title="SourceBox Sentry Command Center API",
    description="FastAPI backend with Clerk authentication for SourceBox Sentry Command Center",
    version="2.1.0",
    lifespan=lifespan,
    # Move FastAPI's auto docs off /docs so the React DocsPage can own that path.
    docs_url="/api-docs",
    redoc_url="/api-redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 response — gives the client everything it needs to retry.

    The slowapi default emits a bare `{"detail": "429 ..."}` string with no
    Retry-After header, which leaves integrators guessing at the backoff
    window and which limit they hit. We return:
      - a stable JSON shape matching the rest of the API's error envelope
      - the exact limit string (e.g. "60 per 1 minute") so callers know what
        bucket they tripped
      - a `Retry-After: 60` header, per RFC 9110, so off-the-shelf HTTP
        clients back off without special handling
    60s is a safe upper bound because our tightest rate windows are minute-
    scoped; callers that honour Retry-After will idle through the window and
    succeed on the next attempt.
    """
    limit_str = str(exc.detail) if getattr(exc, "detail", None) else "rate limit exceeded"
    body = {
        "error": "rate_limit_exceeded",
        "message": (
            "Too many requests. Back off and retry after the Retry-After window. "
            "See /docs#api-rate-limits for per-route limits."
        ),
        "limit": limit_str,
        "retry_after_seconds": 60,
    }
    return JSONResponse(status_code=429, content=body, headers={"Retry-After": "60"})


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ── Pydantic validation errors → ApiError envelope ──────────────────
#
# FastAPI's default 422 body for a request that fails Pydantic
# validation is a list of dicts:
#
#     {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}
#
# That's machine-friendly but unreadable to a human, and the frontend's
# error parser used to stringify the array into something like
# "[object Object]" before we taught it about the shape.  Funnel
# validation failures through the same envelope ApiError uses, so the
# REST surface produces one shape regardless of whether the failure
# came from a hand-raised exception or Pydantic's auto-validation.
#
# Behaviour on the frontend stays consistent: services/api.js looks at
# body.detail.message and shows it as-is.  Test code can still inspect
# body.detail.errors for the structured per-field breakdown.
from fastapi.exceptions import RequestValidationError  # noqa: E402

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Rewrite Pydantic 422 envelope to match ApiError's shape."""
    errors = exc.errors()
    # Build a one-line summary out of the first failing field — that's
    # what gets shown in the toast.  The full error list is preserved
    # under detail.errors for callers (and tests) that want the breakdown.
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = first.get("msg", "Validation failed")
        summary = f"{msg} ({loc})" if loc else msg
    else:
        summary = "Request validation failed"
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "error": "validation_failed",
                "message": summary,
                "errors": errors,  # full list for clients that want it
            },
        },
    )

# Get frontend URL from environment (set in fly.toml or .env)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Validate FRONTEND_URL format — a malformed value (missing scheme,
# trailing slash, embedded whitespace) would silently widen CORS or
# quietly fail to match the real origin header.  Log loud and drop it
# so we don't ship an ambiguous allow-list to production.
def _validate_frontend_url(url: str) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not (url.startswith("http://") or url.startswith("https://")):
        logger.warning(
            "[Startup] FRONTEND_URL=%r must start with http:// or https:// — ignoring",
            url,
        )
        return None
    # Reject trailing slashes — CORS origin compares exact strings.
    if url.endswith("/"):
        url = url.rstrip("/")
    # Reject embedded whitespace or commas (likely misconfigured list).
    if any(c.isspace() for c in url) or "," in url:
        logger.warning(
            "[Startup] FRONTEND_URL=%r contains whitespace or comma — ignoring",
            url,
        )
        return None
    return url


frontend_url = _validate_frontend_url(frontend_url)

# CORS configuration - include both local and production URLs
cors_origins = [
    "http://localhost:5173",
    "http://localhost:8000",
    "https://opensentry-command.fly.dev",
]

if frontend_url and frontend_url not in cors_origins:
    cors_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Node-API-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https" or os.getenv("FLY_APP_NAME"):
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# Include API routers
app.include_router(cameras.router)
app.include_router(webhooks.router)
app.include_router(nodes.router)
app.include_router(audit.router)
app.include_router(hls.router)
app.include_router(ws.router)
app.include_router(install.router)
app.include_router(mcp_keys.router)
app.include_router(mcp_activity.router)
app.include_router(incidents.router)
app.include_router(motion.router)
app.include_router(notifications.router)

# Mount MCP server at /mcp
app.mount("/mcp", mcp_app)


# Background-loop constants moved up to just above the ``lifespan``
# function (search "Background-loop tunables") so the f-string in
# ``lifespan`` doesn't reference a name defined later in the module.


def run_log_cleanup(db, *, default_retention_days: int = LOG_RETENTION_DAYS) -> dict:
    """Delete log rows older than each org's tier-specific retention window.

    Extracted from ``_log_cleanup_loop`` so tests can drive it directly
    without waiting for a background tick. Mirrors ``run_offline_sweep``'s
    "synchronous, takes a session, returns a summary" shape — see the
    Sentry alert OPENSENTRY-COMMAND-1 for why exercising this path
    end-to-end matters (the loop's outer ``try/except`` swallowed an
    AttributeError nightly for an unknown stretch before that fired).

    Retention is tiered (Free 30d / Pro 90d / Pro Plus 365d) so cleanup
    has to iterate orgs instead of running one global cutoff query. Orgs
    without a resolvable plan fall back to ``default_retention_days``
    (a parameter for test override; production passes
    ``LOG_RETENTION_DAYS``) so an org we can't look up isn't silently
    kept forever.

    The function form ``union(a, b, c, ...)`` below is the SQLAlchemy
    2.x-compatible way to compose this. The chained form
    ``select(...).union(...).union(...)`` works on the first call
    (returns a ``CompoundSelect``) but the second ``.union()`` raises
    ``AttributeError: 'CompoundSelect' object has no attribute 'union'``
    — that was the production Sentry bug.

    Returns a dict::

        {
            "orgs_processed": int,
            "totals": {"stream", "mcp", "audit", "motion", "notif"},
            "total_deleted": int,
        }
    """
    from sqlalchemy import union, select
    from app.models.models import (
        StreamAccessLog, McpActivityLog, AuditLog, MotionEvent, Notification,
    )
    from app.core.plans import get_plan_limits, resolve_org_plan

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    # One query collects every org_id we're holding logs for.
    # UNION across the log tables — small set, runs once a day.
    org_rows = db.execute(
        union(
            select(StreamAccessLog.org_id).distinct(),
            select(McpActivityLog.org_id).distinct(),
            select(AuditLog.org_id).distinct(),
            select(MotionEvent.org_id).distinct(),
            select(Notification.org_id).distinct(),
        )
    ).all()
    org_ids = {row[0] for row in org_rows if row[0]}

    totals = {"stream": 0, "mcp": 0, "audit": 0, "motion": 0, "notif": 0}
    for org_id in org_ids:
        try:
            plan = resolve_org_plan(db, org_id)
        except Exception:
            plan = "free_org"
        retention_days = get_plan_limits(plan).get(
            "log_retention_days", default_retention_days,
        )
        cutoff = now - timedelta(days=retention_days)

        totals["stream"] += (
            db.query(StreamAccessLog)
            .filter(StreamAccessLog.org_id == org_id, StreamAccessLog.accessed_at < cutoff)
            .delete(synchronize_session=False)
        )
        totals["mcp"] += (
            db.query(McpActivityLog)
            .filter(McpActivityLog.org_id == org_id, McpActivityLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        totals["audit"] += (
            db.query(AuditLog)
            .filter(AuditLog.org_id == org_id, AuditLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        totals["motion"] += (
            db.query(MotionEvent)
            .filter(MotionEvent.org_id == org_id, MotionEvent.timestamp < cutoff)
            .delete(synchronize_session=False)
        )
        totals["notif"] += (
            db.query(Notification)
            .filter(Notification.org_id == org_id, Notification.created_at < cutoff)
            .delete(synchronize_session=False)
        )

    db.commit()

    return {
        "orgs_processed": len(org_ids),
        "totals": totals,
        "total_deleted": sum(totals.values()),
    }


async def _log_cleanup_loop():
    """Background task: delete old logs per-org using the caller's plan's
    retention setting, and free segment caches for cameras that have been
    offline.

    The actual work lives in ``run_log_cleanup`` (log retention) and the
    inline inactive-camera-cache block below — keeping the loop itself
    a thin scheduler makes the testable parts testable.
    """
    from app.models.models import Camera

    while True:
        await asyncio.sleep(LOG_CLEANUP_INTERVAL_HOURS * 3600)

        # ── Log retention cleanup (per-org, tiered) ───────────────
        try:
            db = SessionLocal()
            try:
                summary = run_log_cleanup(db)
                if summary["total_deleted"] > 0:
                    t = summary["totals"]
                    logger.info(
                        "[Cleanup] Deleted %d old logs across %d orgs (stream=%d mcp=%d audit=%d motion=%d notif=%d)",
                        summary["total_deleted"], summary["orgs_processed"],
                        t["stream"], t["mcp"], t["audit"], t["motion"], t["notif"],
                    )
            finally:
                db.close()
        except Exception:
            logger.exception("[Cleanup] Log cleanup failed")

        # ── Inactive camera cache cleanup ─────────────────────────
        # Free in-memory segment/playlist caches for cameras that
        # have been offline longer than the threshold.
        try:
            from app.api.hls import cleanup_camera_cache
            inactive_cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
                hours=INACTIVE_CAMERA_CLEANUP_HOURS
            )
            db = SessionLocal()
            try:
                inactive_cameras = (
                    db.query(Camera)
                    .filter(Camera.last_seen < inactive_cutoff)
                    .all()
                )
                if inactive_cameras:
                    for cam in inactive_cameras:
                        cleanup_camera_cache(cam.camera_id)
                    logger.info(
                        "[Cleanup] Cleared caches for %d inactive cameras (offline >%dh)",
                        len(inactive_cameras), INACTIVE_CAMERA_CLEANUP_HOURS,
                    )
            finally:
                db.close()
        except Exception:
            logger.exception("[Cleanup] Inactive camera cleanup failed")


def run_offline_sweep(db, *, heartbeat_timeout_seconds: int = OFFLINE_HEARTBEAT_TIMEOUT_SECONDS) -> dict:
    """Flip nodes/cameras from ``status='online'`` to ``'offline'`` when their
    last heartbeat is older than the threshold, emitting notifications for
    each transition.

    Extracted from the loop so tests can drive it directly without
    waiting for a background task tick.  Returns a summary dict with
    counts of nodes/cameras flipped — useful for tests and logging.
    """
    from app.models.models import CameraNode, Camera
    from app.api.notifications import emit_camera_transition, emit_node_transition

    cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=heartbeat_timeout_seconds
    )

    # Find stale nodes first so we can emit admin notifications for them.
    # Queried with last_seen != None — a row with null last_seen hasn't
    # been heard from yet; if its status is "online" that's a bug, but
    # we'll leave it alone rather than emit a spurious "went offline".
    stale_nodes = (
        db.query(CameraNode)
        .filter(
            CameraNode.status == "online",
            CameraNode.last_seen.isnot(None),
            CameraNode.last_seen < cutoff,
        )
        .all()
    )
    node_transitions: list[tuple[str, str, str]] = []  # (node_id, org_id, display_name)
    for node in stale_nodes:
        node.status = "offline"
        node_transitions.append((node.node_id, node.org_id, node.name or node.node_id))

    stale_cameras = (
        db.query(Camera)
        .filter(
            Camera.status == "online",
            Camera.last_seen.isnot(None),
            Camera.last_seen < cutoff,
        )
        .all()
    )
    camera_transitions: list[tuple[str, str, str, Optional[str]]] = []
    for cam in stale_cameras:
        cam.status = "offline"
        parent_node_id = cam.node.node_id if cam.node else None
        display = cam.name or cam.camera_id
        camera_transitions.append((cam.camera_id, cam.org_id, display, parent_node_id))

    db.commit()

    # Emit AFTER commit so the notification never references a row that
    # got rolled back.
    for nid, oid, name in node_transitions:
        try:
            emit_node_transition(
                db, node_id=nid, org_id=oid, display_name=name, new_status="offline"
            )
        except Exception:
            logger.exception("[OfflineSweep] Failed to emit node transition for %s", nid)

    for cid, oid, name, parent in camera_transitions:
        try:
            emit_camera_transition(
                db,
                camera_id=cid,
                org_id=oid,
                display_name=name,
                new_status="offline",
                node_id=parent,
            )
        except Exception:
            logger.exception("[OfflineSweep] Failed to emit camera transition for %s", cid)

    return {
        "nodes_flipped": len(node_transitions),
        "cameras_flipped": len(camera_transitions),
    }


async def _viewer_usage_flush_loop():
    """Background task — flush per-org viewer-second counters to the DB.

    Runs every 60 seconds. Batching keeps the hot HLS-serve path O(1) in
    memory and amortizes writes to one UPSERT per active org per minute
    rather than one per segment.
    """
    # Imported lazily so test environments that don't import app.api.hls
    # at all don't pay the module-import cost.
    while True:
        await asyncio.sleep(60)
        try:
            from app.api.hls import flush_viewer_usage
            # flush_viewer_usage does its own DB session + error handling;
            # we only care whether anything was written so we can log it.
            await asyncio.to_thread(flush_viewer_usage)
        except Exception:
            logger.exception("[ViewerUsage] Flush loop tick failed")


async def _offline_sweep_loop():
    """Background task — periodically flip stale 'online' rows to 'offline'.

    A heart-beating node sends status updates every ~30s over WebSocket;
    if it crashes, the DB would sit at ``status='online'`` indefinitely
    and no transition notification would ever fire.  This sweep closes
    that gap.
    """
    # Defer imports so test environments without a full app don't choke.
    while True:
        await asyncio.sleep(OFFLINE_SWEEP_INTERVAL_SECONDS)
        try:
            db = SessionLocal()
            try:
                summary = run_offline_sweep(db)
                total = summary["nodes_flipped"] + summary["cameras_flipped"]
                if total > 0:
                    logger.info(
                        "[OfflineSweep] Flipped %d entities to offline (nodes=%d, cameras=%d)",
                        total, summary["nodes_flipped"], summary["cameras_flipped"],
                    )
            finally:
                db.close()
        except Exception:
            logger.exception("[OfflineSweep] Sweep failed")


# Serve static files from the React build
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        # Let API, WebSocket, and install routes pass through. /docs is owned by
        # the React DocsPage; FastAPI's auto docs live at /api-docs (see ctor).
        # /downloads/ is the backend binary-redirect route (see install.py);
        # without it, /downloads/linux/x86_64 would fall through to the SPA.
        if request.url.path.startswith(("/api", "/ws", "/install.", "/mcp-setup.", "/downloads/")):
            return await call_next(request)

        # MCP endpoint: only pass POST requests (JSON-RPC) to the MCP server;
        # GET /mcp should serve the frontend dashboard page
        if request.url.path.startswith("/mcp") and request.method == "POST":
            return await call_next(request)

        static_file = static_dir / request.url.path.lstrip("/")
        if static_file.exists() and static_file.is_file():
            return FileResponse(static_file)

        if not request.url.path.startswith("/api"):
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)

        return await call_next(request)


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "2.1.0"}


@app.get("/api/health/detailed")
async def health_check_detailed():
    """Verbose health/status endpoint — intended for status-page polling
    and on-call diagnostics, not for load balancers (those should poll
    ``/api/health`` so a slow DB doesn't cascade into removing the
    machine from rotation).

    Public on purpose: a status page tool needs to read it from off-net,
    and the surface here is deliberately metric-shaped — DB ping ms,
    cache occupancy counts, queue depths — never org IDs, camera IDs,
    user emails, or anything that would leak business intelligence to
    a competitor scraping the endpoint.

    Status semantics:
      - "healthy"    — every check passed.
      - "degraded"   — non-critical subsystem reporting a warning (e.g.
                       a viewer-usage flush queue that's growing faster
                       than it drains). The app still serves traffic
                       correctly; just keep an eye on it.
      - "unhealthy"  — DB ping failed. The app is up but cannot serve
                       most reads/writes. Pages should fire.
    """
    from sqlalchemy import text
    # Defer import: hls.py pulls in storage helpers that are heavier
    # than this endpoint should pay for on cold start.
    from app.api.hls import (
        _playlist_cache,
        _segment_cache,
        _pending_viewer_seconds,
    )
    from app.api.notifications import notification_broadcaster

    now_wall = datetime.now(tz=timezone.utc)
    uptime_s = round(time.monotonic() - _STARTED_AT_MONO, 3)

    # ── Database ping ────────────────────────────────────────
    # ``SELECT 1`` is the cheapest round-trip that proves the connection
    # is live + the DB is responding. Time it so a slow DB shows up as a
    # latency spike before it tips over into errors.
    db_check: dict = {"status": "ok"}
    try:
        db = SessionLocal()
        try:
            t0 = time.perf_counter()
            db.execute(text("SELECT 1"))
            db_check["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        finally:
            db.close()
    except Exception as exc:
        # Don't surface the exception text — it can include connection
        # strings or hostnames. Generic class name is enough for triage.
        db_check = {"status": "error", "error_class": type(exc).__name__}
        logger.warning("[Health] DB ping failed", exc_info=True)

    # ── In-memory subsystem snapshots ────────────────────────
    # All read without locks: a momentary inconsistency in a count is
    # fine for a status page; not worth blocking the hot path.
    hls_cache = {
        "status": "ok",
        "playlists_cached": len(_playlist_cache),
        "segment_cameras": len(_segment_cache),
    }

    pending_views = sum(_pending_viewer_seconds.values())
    viewer_usage = {
        "status": "ok",
        "pending_writes": pending_views,
    }
    # The flush loop ticks every 60s; if pending grows past a threshold
    # the loop is probably failing silently. ``warn`` doesn't gate
    # liveness — the app keeps serving — but a status page would render
    # this as yellow.
    if pending_views > 100_000:
        viewer_usage["status"] = "warn"

    sse = {
        "status": "ok",
        "subscriber_orgs": len(notification_broadcaster._subscribers),
        "subscriber_total": sum(
            len(s) for s in notification_broadcaster._subscribers.values()
        ),
    }

    # ── Roll up overall status ───────────────────────────────
    if db_check["status"] != "ok":
        overall = "unhealthy"
    elif viewer_usage["status"] == "warn":
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "version": "2.1.0",
        "uptime_seconds": uptime_s,
        "started_at": _STARTED_AT_WALL.isoformat(),
        "time": now_wall.isoformat(),
        "checks": {
            "database": db_check,
            "hls_cache": hls_cache,
            "viewer_usage": viewer_usage,
            "sse": sse,
        },
    }
