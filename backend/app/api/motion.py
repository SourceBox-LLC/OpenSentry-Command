"""
Motion Events API — query motion detection events reported by CloudNodes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_view
from app.core.database import get_db
from app.models.models import MotionEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/motion", tags=["motion"])


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
