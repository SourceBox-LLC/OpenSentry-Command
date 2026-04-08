from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_admin, AuthUser
from app.models import StreamAccessLog

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit/stream-logs")
async def get_stream_logs(
    camera_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    admin: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get stream access logs for the admin's organization.
    Only org admins can access this endpoint.
    Logs are automatically cleaned up after the retention period.
    """
    query = db.query(StreamAccessLog).filter(StreamAccessLog.org_id == admin.org_id)

    if camera_id:
        query = query.filter(StreamAccessLog.camera_id == camera_id)

    if user_id:
        query = query.filter(StreamAccessLog.user_id == user_id)

    total = query.count()

    logs = (
        query.order_by(StreamAccessLog.accessed_at.desc())
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


@router.get("/audit/stream-logs/stats")
async def get_stream_stats(
    days: int = Query(default=7, le=30),
    admin: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get stream access statistics for the admin's organization.
    Returns counts by camera, user, and day.
    """
    from sqlalchemy import func

    since = datetime.utcnow() - timedelta(days=days)

    base_query = db.query(StreamAccessLog).filter(
        StreamAccessLog.org_id == admin.org_id,
        StreamAccessLog.accessed_at >= since,
    )

    by_camera = (
        base_query.with_entities(
            StreamAccessLog.camera_id, func.count(StreamAccessLog.id).label("count")
        )
        .group_by(StreamAccessLog.camera_id)
        .order_by(func.count(StreamAccessLog.id).desc())
        .limit(10)
        .all()
    )

    by_user = (
        base_query.with_entities(
            StreamAccessLog.user_id,
            StreamAccessLog.user_email,
            func.count(StreamAccessLog.id).label("count"),
        )
        .group_by(StreamAccessLog.user_id, StreamAccessLog.user_email)
        .order_by(func.count(StreamAccessLog.id).desc())
        .limit(10)
        .all()
    )

    by_day = (
        base_query.with_entities(
            func.date(StreamAccessLog.accessed_at).label("date"),
            func.count(StreamAccessLog.id).label("count"),
        )
        .group_by(func.date(StreamAccessLog.accessed_at))
        .order_by(func.date(StreamAccessLog.accessed_at).desc())
        .all()
    )

    return {
        "days": days,
        "total_accesses": base_query.count(),
        "by_camera": [{"camera_id": c, "count": n} for c, n in by_camera],
        "by_user": [{"user_id": u, "user_email": e or "", "count": n} for u, e, n in by_user],
        "by_day": [{"date": str(d), "count": n} for d, n in by_day],
    }
