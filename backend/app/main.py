import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.api import cameras, webhooks, nodes, streams, audit, hls, ws, install

Base.metadata.create_all(bind=engine)

limiter = Limiter(key_func=lambda: "default")

app = FastAPI(
    title="OpenSentry Command Center API",
    description="FastAPI backend with Clerk authentication for OpenSentry Command Center",
    version="2.0.0",
)

app.state.limiter = limiter
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
        if request.url.path.startswith(("/api", "/ws", "/install.")):
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
