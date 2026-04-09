import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.core.limiter import limiter
from app.api import cameras, webhooks, nodes, streams, audit, hls, ws, install, mcp_keys
from app.mcp.server import mcp

Base.metadata.create_all(bind=engine)

# Migrate existing tables: add columns that create_all won't add to existing tables.
from sqlalchemy import inspect, text
with engine.connect() as conn:
    columns = [c["name"] for c in inspect(engine).get_columns("stream_access_logs")]
    if "user_email" not in columns:
        conn.execute(text("ALTER TABLE stream_access_logs ADD COLUMN user_email VARCHAR(255) DEFAULT ''"))
        conn.commit()

# Build the MCP ASGI app — path="/" because the mount prefix handles /mcp
mcp_app = mcp.http_app(path="/", stateless_http=True)

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
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(cameras.router)
app.include_router(webhooks.router)
app.include_router(nodes.router)
app.include_router(streams.router)
app.include_router(audit.router)
app.include_router(hls.router)
app.include_router(ws.router)
app.include_router(install.router)
app.include_router(mcp_keys.router)

# Mount MCP server at /mcp
app.mount("/mcp", mcp_app)


@app.on_event("startup")
async def startup_event():
    """Initialize application."""
    print("[App] OpenSentry Command Center started (Clerk Auth enabled)")


@app.on_event("shutdown")
async def shutdown_event():
    print("[System] Shutdown complete")


# Serve static files from the React build
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        if request.url.path.startswith(("/api", "/ws", "/mcp", "/install.")):
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
