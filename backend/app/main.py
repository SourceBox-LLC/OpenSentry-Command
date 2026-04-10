import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.limiter import limiter
from app.api import cameras, webhooks, nodes, audit, hls, ws, install, mcp_keys, mcp_activity
from app.mcp.server import mcp

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

# Migrate existing tables: add columns that create_all won't add to existing tables.
from sqlalchemy import inspect as sa_inspect, text
try:
    with engine.connect() as conn:
        columns = [c["name"] for c in sa_inspect(engine).get_columns("stream_access_logs")]
        if "user_email" not in columns:
            conn.execute(text("ALTER TABLE stream_access_logs ADD COLUMN user_email VARCHAR(255) DEFAULT ''"))
            conn.commit()
except Exception:
    pass  # Table doesn't exist yet (fresh DB) — create_all handles it

# Drop the orphaned pending_uploads table (dead code removed in cleanup).
try:
    with engine.connect() as conn:
        tables = sa_inspect(engine).get_table_names()
        if "pending_uploads" in tables:
            conn.execute(text("DROP TABLE pending_uploads"))
            conn.commit()
            logger.info("Dropped orphaned pending_uploads table")
except Exception:
    pass

# Build the MCP ASGI app — path="/" because the mount prefix handles /mcp
mcp_app = mcp.http_app(path="/", stateless_http=True, json_response=True)

app = FastAPI(
    title="OpenSentry Command Center API",
    description="FastAPI backend with Clerk authentication for OpenSentry Command Center",
    version="2.0.0",
    lifespan=mcp_app.lifespan,  # Required for MCP session manager
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Get frontend URL from environment (set in fly.toml or .env)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

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
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Node-API-Key"],
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

# Mount MCP server at /mcp
app.mount("/mcp", mcp_app)


# Default retention: 90 days for all log types
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "90"))
LOG_CLEANUP_INTERVAL_HOURS = 24  # Run once per day
# Cameras offline for longer than this get their Tigris segments cleaned up.
# HLS segments are live-only fragments — useless once streaming stops.
INACTIVE_CAMERA_CLEANUP_HOURS = int(os.getenv("INACTIVE_CAMERA_CLEANUP_HOURS", "24"))


async def _log_cleanup_loop():
    """Background task: delete logs older than retention period
    and clean up Tigris storage for cameras that have been offline."""
    from app.models.models import StreamAccessLog, McpActivityLog, AuditLog, Camera

    while True:
        await asyncio.sleep(LOG_CLEANUP_INTERVAL_HOURS * 3600)

        # ── Log retention cleanup ──────────────────────────────────
        try:
            cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=LOG_RETENTION_DAYS)
            db = SessionLocal()
            try:
                stream_count = db.query(StreamAccessLog).filter(StreamAccessLog.accessed_at < cutoff).delete()
                mcp_count = db.query(McpActivityLog).filter(McpActivityLog.timestamp < cutoff).delete()
                audit_count = db.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
                db.commit()
                total = stream_count + mcp_count + audit_count
                if total > 0:
                    logger.info(
                        "[Cleanup] Deleted %d old logs (stream=%d, mcp=%d, audit=%d, retention=%dd)",
                        total, stream_count, mcp_count, audit_count, LOG_RETENTION_DAYS,
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


@app.on_event("startup")
async def startup_event():
    """Initialize application."""
    asyncio.create_task(_log_cleanup_loop())
    print(f"[App] OpenSentry Command Center started (log retention: {LOG_RETENTION_DAYS}d)")


@app.on_event("shutdown")
async def shutdown_event():
    print("[System] Shutdown complete")


# Serve static files from the React build
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        # Let API, WebSocket, install, and OpenAPI docs routes pass through
        if request.url.path.startswith(("/api", "/ws", "/install.", "/mcp-setup.", "/docs", "/redoc", "/openapi.json")):
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
