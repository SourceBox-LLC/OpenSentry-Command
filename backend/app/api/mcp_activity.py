"""
MCP Activity API — SSE streaming + REST endpoints for live MCP monitoring,
plus DB-backed endpoints for persistent audit logs.

The MCP dashboard connects here to see real-time tool calls,
active client sessions, and aggregate stats.
The admin dashboard uses the /logs and /logs/stats endpoints for historical data.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_admin
from app.core.database import get_db
from app.models.models import McpActivityLog
from app.mcp.activity import MAX_SSE_SUBSCRIBERS_PER_ORG, tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp/activity", tags=["mcp-activity"])


@router.get("/stream")
async def stream_activity(user: AuthUser = Depends(require_admin)):
    """
    SSE endpoint — streams MCP tool call events in real-time.
    Each event is a JSON-encoded McpEvent.
    """
    from app.core.plans import get_plan_limits
    org_id = user.org_id
    cap = get_plan_limits(user.plan).get("max_sse_subscribers", MAX_SSE_SUBSCRIBERS_PER_ORG)
    queue = tracker.subscribe(org_id, cap)
    if queue is None:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many open MCP activity streams for this org (cap: "
                f"{cap} on your current plan). Close unused tabs and retry, "
                f"or upgrade for a higher cap."
            ),
        )

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
    # Cap matches the in-memory tracker's bounded buffer size; without a
    # `le` an accidental `limit=10000` would silently be clamped inside
    # the tracker, but returning a 422 here keeps the contract honest.
    limit: int = Query(default=50, ge=1, le=500),
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


# ---------------------------------------------------------------------------
# DB-backed endpoints — persistent MCP audit logs for admin dashboard
# ---------------------------------------------------------------------------


@router.get("/logs")
async def get_mcp_logs(
    tool_name: Optional[str] = None,
    key_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    # OFFSET is O(n) — cap so no one can force SQLite to skip billions.
    offset: int = Query(default=0, ge=0, le=1_000_000),
    admin: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get persisted MCP activity logs with filtering and pagination."""
    query = db.query(McpActivityLog).filter(McpActivityLog.org_id == admin.org_id)

    if tool_name:
        query = query.filter(McpActivityLog.tool_name == tool_name)
    if key_name:
        query = query.filter(McpActivityLog.key_name.ilike(f"%{key_name}%"))
    if status:
        query = query.filter(McpActivityLog.status == status)

    total = query.count()
    logs = (
        query.order_by(McpActivityLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [log.to_dict() for log in logs],
    }


@router.get("/logs/stats")
async def get_mcp_log_stats(
    days: int = Query(default=7, le=30),
    admin: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get aggregate MCP activity statistics from persisted logs."""
    from sqlalchemy import func

    since = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    base = db.query(McpActivityLog).filter(
        McpActivityLog.org_id == admin.org_id,
        McpActivityLog.timestamp >= since,
    )

    total = base.count()
    errors = base.filter(McpActivityLog.status == "error").count()

    by_tool = (
        base.with_entities(
            McpActivityLog.tool_name,
            func.count(McpActivityLog.id).label("count"),
        )
        .group_by(McpActivityLog.tool_name)
        .order_by(func.count(McpActivityLog.id).desc())
        .all()
    )

    by_key = (
        base.with_entities(
            McpActivityLog.key_name,
            func.count(McpActivityLog.id).label("count"),
        )
        .group_by(McpActivityLog.key_name)
        .order_by(func.count(McpActivityLog.id).desc())
        .all()
    )

    by_day = (
        base.with_entities(
            func.date(McpActivityLog.timestamp).label("date"),
            func.count(McpActivityLog.id).label("count"),
        )
        .group_by(func.date(McpActivityLog.timestamp))
        .order_by(func.date(McpActivityLog.timestamp).desc())
        .all()
    )

    return {
        "days": days,
        "total_calls": total,
        "total_errors": errors,
        "by_tool": [{"tool_name": t, "count": n} for t, n in by_tool],
        "by_key": [{"key_name": k, "count": n} for k, n in by_key],
        "by_day": [{"date": str(d), "count": n} for d, n in by_day],
    }
