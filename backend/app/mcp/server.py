"""
OpenSentry MCP Server — gives AI tools (Claude Code, etc.) direct access
to an organization's cameras, nodes, streams, and settings.

Mounted inside the main FastAPI app at /mcp.
Auth: Bearer token using org-scoped MCP API keys.
Rate limited per API key based on org plan.
"""

import asyncio
import base64
import collections
import contextvars
import functools
import hashlib
import logging
import threading
import time
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import (
    Camera,
    CameraGroup,
    CameraNode,
    McpApiKey,
    Setting,
    StreamAccessLog,
)
from app.services.storage import get_storage
from app.mcp.activity import tracker, McpEvent

logger = logging.getLogger(__name__)

# Context variables — set by _auth(), read by the tracking decorator
_ctx_org_id = contextvars.ContextVar("mcp_org_id", default="")
_ctx_key_name = contextvars.ContextVar("mcp_key_name", default="")

# ---------------------------------------------------------------------------
# Per-key rate limiter — sliding window (calls per minute)
# ---------------------------------------------------------------------------

# Plan-based rate limits (calls per minute per API key)
# Keys must match Clerk plan slugs stored in the DB by the webhook handler.
RATE_LIMITS = {
    "pro": 30,
    "business": 120,
}
DEFAULT_RATE_LIMIT = 0  # Block unrecognized plans (MCP requires Pro+)


class _RateLimiter:
    """Thread-safe sliding-window rate limiter keyed by API key hash."""

    def __init__(self):
        # {key_hash: deque of timestamps}
        self._windows: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def check(self, key_hash: str, limit: int, window: int = 60) -> tuple[bool, int]:
        """
        Check if a request is allowed.
        Returns (allowed, remaining_calls).
        """
        now = time.time()
        cutoff = now - window

        with self._lock:
            if key_hash not in self._windows:
                self._windows[key_hash] = collections.deque()

            dq = self._windows[key_hash]

            # Purge old entries
            while dq and dq[0] < cutoff:
                dq.popleft()

            if len(dq) >= limit:
                return False, 0

            dq.append(now)
            return True, limit - len(dq)


_rate_limiter = _RateLimiter()

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "OpenSentry",
    instructions=(
        "You are connected to an OpenSentry Command Center organization. "
        "You can SEE what cameras see via view_camera (returns a live JPEG "
        "snapshot), list cameras, check node status, get stream URLs, manage "
        "recording settings, and view audit logs. All operations are scoped "
        "to the authenticated organization."
    ),
)

# ---------------------------------------------------------------------------
# Auth helper — resolve Bearer token to org_id
# ---------------------------------------------------------------------------

def _resolve_org(headers: dict | None) -> tuple[str, Session]:
    """Validate the Bearer token, enforce rate limit, return (org_id, db_session)."""
    if not headers:
        raise ToolError("Unauthorized: no headers present")

    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ToolError("Unauthorized: missing Bearer token")

    raw_key = auth.split(" ", 1)[1].strip()
    if not raw_key:
        raise ToolError("Unauthorized: empty Bearer token")

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    db = SessionLocal()
    try:
        mcp_key = (
            db.query(McpApiKey)
            .filter_by(key_hash=key_hash, revoked=False)
            .first()
        )
        if not mcp_key:
            db.close()
            raise ToolError("Unauthorized: invalid or revoked API key")

        # Look up org plan and enforce access + rate limit
        plan = Setting.get(db, mcp_key.org_id, "org_plan", "free_org")
        limit = RATE_LIMITS.get(plan)
        if limit is None:
            db.close()
            raise ToolError("MCP requires a Pro or Business plan. Upgrade at /pricing.")
        allowed, remaining = _rate_limiter.check(key_hash, limit)
        if not allowed:
            db.close()
            raise ToolError(
                f"Rate limit exceeded: {limit} calls/min allowed on {plan.title()} plan. "
                "Try again shortly."
            )

        # Touch last_used_at
        mcp_key.last_used_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        db.commit()

        # Set context vars for the activity tracker
        _ctx_org_id.set(mcp_key.org_id)
        _ctx_key_name.set(mcp_key.name)

        return mcp_key.org_id, db
    except ToolError:
        raise
    except Exception:
        db.close()
        raise ToolError("Authentication error")


def _auth():
    """Shortcut: get headers, resolve org, return (org_id, db)."""
    headers = get_http_headers(include={"authorization"})
    return _resolve_org(headers)


# ---------------------------------------------------------------------------
# Activity-tracking decorator — wraps every MCP tool to log calls
# ---------------------------------------------------------------------------

def _summarize_args(kwargs: dict) -> str:
    """Create a short summary of tool arguments for the activity log."""
    parts = []
    for k, v in kwargs.items():
        if v is not None:
            sv = str(v)
            if len(sv) > 30:
                sv = sv[:27] + "..."
            parts.append(f"{k}={sv}")
    return ", ".join(parts) if parts else ""


def tracked(func):
    """Decorator that logs MCP tool calls to the activity tracker."""
    tool_name = func.__name__

    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            event_id = str(uuid_mod.uuid4())[:8]
            start = time.time()
            args_summary = _summarize_args(kwargs)
            try:
                result = await func(*args, **kwargs)
                org_id = _ctx_org_id.get("")
                key_name = _ctx_key_name.get("")
                tracker.log_event(McpEvent(
                    id=event_id,
                    timestamp=start,
                    tool_name=tool_name,
                    org_id=org_id,
                    key_name=key_name,
                    status="completed",
                    duration_ms=round((time.time() - start) * 1000),
                    args_summary=args_summary or None,
                ))
                return result
            except Exception as e:
                org_id = _ctx_org_id.get("")
                key_name = _ctx_key_name.get("")
                tracker.log_event(McpEvent(
                    id=event_id,
                    timestamp=start,
                    tool_name=tool_name,
                    org_id=org_id,
                    key_name=key_name,
                    status="error",
                    duration_ms=round((time.time() - start) * 1000),
                    error=str(e)[:200],
                    args_summary=args_summary or None,
                ))
                raise
        return wrapper
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            event_id = str(uuid_mod.uuid4())[:8]
            start = time.time()
            args_summary = _summarize_args(kwargs)
            try:
                result = func(*args, **kwargs)
                org_id = _ctx_org_id.get("")
                key_name = _ctx_key_name.get("")
                tracker.log_event(McpEvent(
                    id=event_id,
                    timestamp=start,
                    tool_name=tool_name,
                    org_id=org_id,
                    key_name=key_name,
                    status="completed",
                    duration_ms=round((time.time() - start) * 1000),
                    args_summary=args_summary or None,
                ))
                return result
            except Exception as e:
                org_id = _ctx_org_id.get("")
                key_name = _ctx_key_name.get("")
                tracker.log_event(McpEvent(
                    id=event_id,
                    timestamp=start,
                    tool_name=tool_name,
                    org_id=org_id,
                    key_name=key_name,
                    status="error",
                    duration_ms=round((time.time() - start) * 1000),
                    error=str(e)[:200],
                    args_summary=args_summary or None,
                ))
                raise
        return wrapper


# ---------------------------------------------------------------------------
# Camera Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_cameras",
    description="List all cameras in the organization with their current status, codec info, and group assignment.",
    annotations={"readOnlyHint": True},
)
@tracked
def list_cameras() -> list[dict]:
    org_id, db = _auth()
    try:
        cameras = db.query(Camera).filter_by(org_id=org_id).all()
        return [c.to_dict() for c in cameras]
    finally:
        db.close()


@mcp.tool(
    name="get_camera",
    description="Get detailed information about a specific camera by its camera_id.",
    annotations={"readOnlyHint": True},
)
@tracked
def get_camera(
    camera_id: Annotated[str, "The camera_id string (e.g. 'node1-video0')"],
) -> dict:
    org_id, db = _auth()
    try:
        cam = (
            db.query(Camera)
            .filter_by(org_id=org_id, camera_id=camera_id)
            .first()
        )
        if not cam:
            raise ToolError(f"Camera '{camera_id}' not found")
        return cam.to_dict()
    finally:
        db.close()


@mcp.tool(
    name="get_stream_url",
    description=(
        "Get a temporary HLS stream URL for a camera. "
        "The URL is pre-signed and expires after a few minutes. "
        "Use this to watch a live camera feed."
    ),
    annotations={"readOnlyHint": True},
)
@tracked
def get_stream_url(
    camera_id: Annotated[str, "The camera_id to get the stream URL for"],
) -> dict:
    org_id, db = _auth()
    try:
        cam = (
            db.query(Camera)
            .filter_by(org_id=org_id, camera_id=camera_id)
            .first()
        )
        if not cam:
            raise ToolError(f"Camera '{camera_id}' not found")

        storage = get_storage()
        url = storage.generate_stream_url(camera_id, org_id)
        return {
            "camera_id": camera_id,
            "stream_url": url,
            "format": "HLS",
            "note": "URL expires in ~5 minutes. Open in a browser or HLS player.",
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Visual Access Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="view_camera",
    description=(
        "See what a camera sees RIGHT NOW. Returns a live JPEG snapshot image "
        "from the camera. The camera node must be online and actively streaming. "
        "Use this to visually inspect a camera feed."
    ),
    annotations={"readOnlyHint": True},
)
@tracked
async def view_camera(
    camera_id: Annotated[str, "The camera_id to view (e.g. 'node1-video0')"],
) -> Image:
    org_id, db = _auth()
    try:
        cam = (
            db.query(Camera)
            .filter_by(org_id=org_id, camera_id=camera_id)
            .first()
        )
        if not cam:
            raise ToolError(f"Camera '{camera_id}' not found")

        node = db.query(CameraNode).filter_by(id=cam.node_id).first()
        if not node:
            raise ToolError(f"Camera '{camera_id}' has no assigned node")

        node_id = node.node_id
    finally:
        db.close()

    # Send take_snapshot command to CloudNode via WebSocket
    from app.api.ws import manager

    if not manager.is_connected(node_id):
        raise ToolError(f"Node '{node_id}' is offline — cannot capture snapshot")

    try:
        result = await manager.send_command(
            node_id, "take_snapshot", {"camera_id": camera_id}, timeout=15.0,
        )
    except TimeoutError:
        raise ToolError("Snapshot timed out — camera node did not respond in time")
    except ValueError as e:
        raise ToolError(str(e))

    image_b64 = result.get("data", {}).get("image_b64") or result.get("image_b64")
    if not image_b64:
        raise ToolError("Camera node did not return image data — update CloudNode to latest version")

    return Image(data=base64.b64decode(image_b64), format="jpeg")


@mcp.tool(
    name="watch_camera",
    description=(
        "Take multiple snapshots from a camera over a time period to observe "
        "activity or changes. Returns a series of JPEG images. "
        "Useful for monitoring movement or verifying camera coverage."
    ),
    annotations={"readOnlyHint": True},
)
@tracked
async def watch_camera(
    camera_id: Annotated[str, "The camera_id to watch"],
    count: Annotated[int, Field(description="Number of snapshots to take", ge=2, le=10)] = 3,
    interval_seconds: Annotated[int, Field(description="Seconds between snapshots", ge=1, le=30)] = 5,
):
    org_id, db = _auth()
    try:
        cam = (
            db.query(Camera)
            .filter_by(org_id=org_id, camera_id=camera_id)
            .first()
        )
        if not cam:
            raise ToolError(f"Camera '{camera_id}' not found")

        node = db.query(CameraNode).filter_by(id=cam.node_id).first()
        if not node:
            raise ToolError(f"Camera '{camera_id}' has no assigned node")

        node_id = node.node_id
    finally:
        db.close()

    from app.api.ws import manager

    if not manager.is_connected(node_id):
        raise ToolError(f"Node '{node_id}' is offline — cannot capture snapshots")

    results = []
    for i in range(count):
        if i > 0:
            await asyncio.sleep(interval_seconds)
        try:
            result = await manager.send_command(
                node_id, "take_snapshot", {"camera_id": camera_id}, timeout=15.0,
            )
            image_b64 = result.get("data", {}).get("image_b64") or result.get("image_b64")
            if image_b64:
                results.append(Image(data=base64.b64decode(image_b64), format="jpeg"))
            else:
                results.append(f"[Frame {i+1}] No image data returned")
        except (TimeoutError, ValueError) as e:
            results.append(f"[Frame {i+1}] Failed: {e}")

    if not any(isinstance(r, Image) for r in results):
        raise ToolError("Failed to capture any snapshots — check node status")

    return results


# ---------------------------------------------------------------------------
# Camera Group Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_camera_groups",
    description="List all camera groups in the organization.",
    annotations={"readOnlyHint": True},
)
@tracked
def list_camera_groups() -> list[dict]:
    org_id, db = _auth()
    try:
        groups = db.query(CameraGroup).filter_by(org_id=org_id).all()
        return [g.to_dict() for g in groups]
    finally:
        db.close()




# ---------------------------------------------------------------------------
# Node Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_nodes",
    description="List all camera nodes in the organization with status and camera count.",
    annotations={"readOnlyHint": True},
)
@tracked
def list_nodes() -> list[dict]:
    org_id, db = _auth()
    try:
        nodes = db.query(CameraNode).filter_by(org_id=org_id).all()
        return [n.to_dict() for n in nodes]
    finally:
        db.close()


@mcp.tool(
    name="get_node",
    description="Get detailed information about a specific camera node.",
    annotations={"readOnlyHint": True},
)
@tracked
def get_node(
    node_id: Annotated[str, "The node_id string (8-char UUID prefix)"],
) -> dict:
    org_id, db = _auth()
    try:
        node = (
            db.query(CameraNode)
            .filter_by(org_id=org_id, node_id=node_id)
            .first()
        )
        if not node:
            raise ToolError(f"Node '{node_id}' not found")
        return node.to_dict()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Recording Settings Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_recording_settings",
    description="Get current recording settings: continuous 24/7 mode, scheduled recording, and schedule times.",
    annotations={"readOnlyHint": True},
)
@tracked
def get_recording_settings() -> dict:
    org_id, db = _auth()
    try:
        return {
            "continuous_24_7": Setting.get(db, org_id, "continuous_24_7", "false") == "true",
            "scheduled_recording": Setting.get(db, org_id, "scheduled_recording", "false") == "true",
            "scheduled_start": Setting.get(db, org_id, "scheduled_start", "00:00"),
            "scheduled_end": Setting.get(db, org_id, "scheduled_end", "06:00"),
        }
    finally:
        db.close()




# ---------------------------------------------------------------------------
# Audit / Stream Log Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_stream_logs",
    description="Get recent stream access logs showing who watched which camera and when.",
    annotations={"readOnlyHint": True},
)
@tracked
def get_stream_logs(
    camera_id: Annotated[str | None, "Filter by camera_id"] = None,
    limit: Annotated[int, Field(description="Max results", ge=1, le=500)] = 50,
) -> list[dict]:
    org_id, db = _auth()
    try:
        query = db.query(StreamAccessLog).filter_by(org_id=org_id)
        if camera_id:
            query = query.filter_by(camera_id=camera_id)
        logs = query.order_by(StreamAccessLog.accessed_at.desc()).limit(limit).all()
        return [log.to_dict() for log in logs]
    finally:
        db.close()


@mcp.tool(
    name="get_stream_stats",
    description="Get aggregated stream access statistics: total views, views by camera, views by user, views by day.",
    annotations={"readOnlyHint": True},
)
@tracked
def get_stream_stats(
    days: Annotated[int, Field(description="Number of days to look back", ge=1, le=30)] = 7,
) -> dict:
    org_id, db = _auth()
    try:
        from sqlalchemy import func

        cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        base = db.query(StreamAccessLog).filter(
            StreamAccessLog.org_id == org_id,
            StreamAccessLog.accessed_at >= cutoff,
        )
        total = base.count()

        by_camera = (
            base.with_entities(
                StreamAccessLog.camera_id,
                func.count(StreamAccessLog.id).label("views"),
            )
            .group_by(StreamAccessLog.camera_id)
            .all()
        )

        by_user = (
            base.with_entities(
                StreamAccessLog.user_id,
                StreamAccessLog.user_email,
                func.count(StreamAccessLog.id).label("views"),
            )
            .group_by(StreamAccessLog.user_id, StreamAccessLog.user_email)
            .all()
        )

        return {
            "days": days,
            "total_views": total,
            "by_camera": [
                {"camera_id": cid, "views": v} for cid, v in by_camera
            ],
            "by_user": [
                {"user_id": uid, "email": email or "", "views": v}
                for uid, email, v in by_user
            ],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# System Overview Tool
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_system_status",
    description=(
        "Get a high-level overview of the organization's OpenSentry system: "
        "total cameras, online/offline counts, node count, and plan info."
    ),
    annotations={"readOnlyHint": True},
)
@tracked
def get_system_status() -> dict:
    org_id, db = _auth()
    try:
        cameras = db.query(Camera).filter_by(org_id=org_id).all()
        nodes = db.query(CameraNode).filter_by(org_id=org_id).all()

        online_cameras = sum(1 for c in cameras if c.effective_status != "offline")
        online_nodes = sum(1 for n in nodes if n.effective_status not in ("offline", "pending"))

        plan = Setting.get(db, org_id, "org_plan", "free_org")

        return {
            "org_id": org_id,
            "plan": plan,
            "cameras": {
                "total": len(cameras),
                "online": online_cameras,
                "offline": len(cameras) - online_cameras,
            },
            "nodes": {
                "total": len(nodes),
                "online": online_nodes,
                "offline": len(nodes) - online_nodes,
            },
        }
    finally:
        db.close()
