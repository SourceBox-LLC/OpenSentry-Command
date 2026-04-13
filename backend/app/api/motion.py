"""
Motion Events API — query motion detection events reported by CloudNodes,
plus SSE streaming for real-time motion alerts in the dashboard.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_view
from app.core.database import get_db
from app.models.models import MotionEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/motion", tags=["motion"])


# ── Motion Event Broadcaster ────────────────────────────────────────
# Lightweight pub/sub that forwards motion events to SSE subscribers.
# Called by ws.py after persisting each motion event to the DB.

class MotionBroadcaster:
    """Push motion events to dashboard SSE connections, scoped by org."""

    def __init__(self):
        # {org_id: [asyncio.Queue, ...]}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def notify(self, org_id: str, event_data: dict):
        """Broadcast a motion event to all SSE subscribers for an org."""
        queues = self._subscribers.get(org_id, [])
        dead = []
        for q in queues:
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                dead.append(q)
        if dead:
            for q in dead:
                try:
                    self._subscribers[org_id].remove(q)
                except (ValueError, KeyError):
                    pass

    def subscribe(self, org_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        if org_id not in self._subscribers:
            self._subscribers[org_id] = []
        self._subscribers[org_id].append(q)
        logger.info("[Motion] SSE subscriber added for org %s (total: %d)",
                    org_id, len(self._subscribers[org_id]))
        return q

    def unsubscribe(self, org_id: str, q: asyncio.Queue):
        if org_id in self._subscribers:
            try:
                self._subscribers[org_id].remove(q)
            except ValueError:
                pass


# Singleton — imported by ws.py to broadcast events.
motion_broadcaster = MotionBroadcaster()


@router.get("/events")
async def list_motion_events(
    camera_id: Optional[str] = None,
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """List recent motion events, optionally filtered by camera."""
    since = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    query = db.query(MotionEvent).filter(
        MotionEvent.org_id == user.org_id,
        MotionEvent.timestamp >= since,
    )

    if camera_id:
        query = query.filter(MotionEvent.camera_id == camera_id)

    total = query.count()
    events = (
        query.order_by(MotionEvent.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "hours": hours,
        "events": [e.to_dict() for e in events],
    }


@router.get("/events/stats")
async def motion_stats(
    hours: int = Query(default=24, le=168),
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Aggregate motion stats per camera over the given time window."""
    from sqlalchemy import func

    since = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    rows = (
        db.query(
            MotionEvent.camera_id,
            func.count(MotionEvent.id).label("count"),
            func.max(MotionEvent.score).label("peak_score"),
            func.max(MotionEvent.timestamp).label("latest"),
        )
        .filter(
            MotionEvent.org_id == user.org_id,
            MotionEvent.timestamp >= since,
        )
        .group_by(MotionEvent.camera_id)
        .all()
    )

    return {
        "hours": hours,
        "cameras": [
            {
                "camera_id": r.camera_id,
                "event_count": r.count,
                "peak_score": r.peak_score,
                "latest": r.latest.isoformat() if r.latest else None,
            }
            for r in rows
        ],
    }


# ── SSE Stream ──────────────────────────────────────────────────────

@router.get("/events/stream")
async def stream_motion_events(user: AuthUser = Depends(require_view)):
    """
    SSE endpoint — streams motion detection events in real-time.
    Used by the dashboard to show instant motion notifications.
    """
    org_id = user.org_id
    queue = motion_broadcaster.subscribe(org_id)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'org_id': org_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive to prevent connection drop
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            motion_broadcaster.unsubscribe(org_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
