"""
MCP Activity API — SSE streaming + REST endpoints for live MCP monitoring.

The MCP dashboard connects here to see real-time tool calls,
active client sessions, and aggregate stats.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.auth import AuthUser, require_admin
from app.mcp.activity import tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp/activity", tags=["mcp-activity"])


@router.get("/stream")
async def stream_activity(user: AuthUser = Depends(require_admin)):
    """
    SSE endpoint — streams MCP tool call events in real-time.
    Each event is a JSON-encoded McpEvent.
    """
    org_id = user.org_id
    queue = tracker.subscribe(org_id)

    async def event_generator():
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'org_id': org_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    payload = event.to_dict()
                    payload["type"] = "tool_call"
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive to prevent connection timeout
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            tracker.unsubscribe(org_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/recent")
async def get_recent_activity(
    limit: int = 50,
    user: AuthUser = Depends(require_admin),
):
    """Get recent MCP tool call events."""
    events = tracker.get_recent_events(user.org_id, limit=limit)
    return [e.to_dict() for e in events]


@router.get("/sessions")
async def get_active_sessions(user: AuthUser = Depends(require_admin)):
    """Get currently active MCP client sessions."""
    return tracker.get_active_sessions(user.org_id)


@router.get("/stats")
async def get_activity_stats(user: AuthUser = Depends(require_admin)):
    """Get aggregate MCP activity statistics."""
    return tracker.get_stats(user.org_id)
