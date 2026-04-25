import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
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


async def _log_cleanup_loop():
    """Background task: delete old logs per-org using the caller's plan's
    retention setting, and free segment caches for cameras that have been
    offline.

    Retention is tiered (Free 30d / Pro 90d / Pro Plus 365d) so cleanup has
    to iterate orgs instead of running one global cutoff query. Orgs without
    a resolvable plan fall back to ``LOG_RETENTION_DAYS`` so an org we can't
    look up isn't silently kept forever.
    """
    from app.models.models import (
        StreamAccessLog, McpActivityLog, AuditLog, MotionEvent, Camera, Notification, Setting,
    )
    from app.core.plans import get_plan_limits, resolve_org_plan

    while True:
        await asyncio.sleep(LOG_CLEANUP_INTERVAL_HOURS * 3600)

        # ── Log retention cleanup (per-org, tiered) ───────────────
        try:
            db = SessionLocal()
            try:
                now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                # One query collects every org_id we're holding logs for.
                # UNION across the log tables — small set, runs once a day.
                from sqlalchemy import union, select
                org_rows = (
                    db.execute(
                        select(StreamAccessLog.org_id).distinct()
                        .union(select(McpActivityLog.org_id).distinct())
                        .union(select(AuditLog.org_id).distinct())
                        .union(select(MotionEvent.org_id).distinct())
                        .union(select(Notification.org_id).distinct())
                    ).all()
                )
                org_ids = {row[0] for row in org_rows if row[0]}

                totals = {"stream": 0, "mcp": 0, "audit": 0, "motion": 0, "notif": 0}
                for org_id in org_ids:
                    try:
                        plan = resolve_org_plan(db, org_id)
                    except Exception:
                        plan = "free_org"
                    retention_days = get_plan_limits(plan).get(
                        "log_retention_days", LOG_RETENTION_DAYS,
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
                total = sum(totals.values())
                if total > 0:
                    logger.info(
                        "[Cleanup] Deleted %d old logs across %d orgs (stream=%d mcp=%d audit=%d motion=%d notif=%d)",
                        total, len(org_ids),
                        totals["stream"], totals["mcp"], totals["audit"], totals["motion"], totals["notif"],
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
