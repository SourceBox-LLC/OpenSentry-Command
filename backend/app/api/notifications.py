"""
Notifications API — unified inbox for user-facing events.

Covers motion detection alerts, camera/node status transitions, and
(future) system errors.  Supports:
  - GET  /api/notifications             list recent, paginated, audience-filtered
  - GET  /api/notifications/unread-count badge count for the bell icon
  - POST /api/notifications/mark-viewed  bump the user's last_viewed_at to now
  - GET  /api/notifications/stream       SSE — live updates for the panel

Read state is per-(clerk_user_id, org_id).  Unread = notifications newer
than the user's last_viewed_at timestamp.

Audience filtering: each notification has ``audience`` set to ``"all"``
(every member sees it) or ``"admin"`` (only admins see it).  Non-admin
users never see ``"admin"`` notifications in their feed or unread count.
"""

import asyncio
import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_view
from app.core.database import SessionLocal, get_db
from app.models.models import Notification, UserNotificationState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── Broadcaster ─────────────────────────────────────────────────────
# Same pattern as motion_broadcaster — one asyncio.Queue per SSE
# subscriber, scoped by org.  Each event also carries the audience so
# the stream generator can filter per subscriber.

class NotificationBroadcaster:
    """Push notification events to inbox SSE subscribers, scoped by org."""

    def __init__(self):
        # {org_id: [(queue, is_admin), ...]}
        self._subscribers: dict[str, list[tuple[asyncio.Queue, bool]]] = {}

    def notify(self, org_id: str, event_data: dict):
        """Broadcast a notification to every SSE subscriber in the org.

        Subscribers get the event only if their role matches the event's
        audience ("all" is delivered to everyone; "admin" only to admins).
        """
        audience = event_data.get("audience", "all")
        subs = self._subscribers.get(org_id, [])
        dead = []
        for q, is_admin in subs:
            if audience == "admin" and not is_admin:
                continue
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                dead.append((q, is_admin))
        if dead:
            for entry in dead:
                try:
                    self._subscribers[org_id].remove(entry)
                except (ValueError, KeyError):
                    pass

    def subscribe(self, org_id: str, is_admin: bool) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(org_id, []).append((q, is_admin))
        logger.info(
            "[Notifications] SSE subscriber added for org %s (admin=%s, total=%d)",
            org_id, is_admin, len(self._subscribers[org_id]),
        )
        return q

    def unsubscribe(self, org_id: str, q: asyncio.Queue):
        subs = self._subscribers.get(org_id)
        if not subs:
            return
        self._subscribers[org_id] = [(qq, adm) for qq, adm in subs if qq is not q]


notification_broadcaster = NotificationBroadcaster()


# ── Service ────────────────────────────────────────────────────────
# Helper that any part of the app can call to emit a notification.
# Handles DB persistence + broadcast.  Swallows errors so a bad
# notification never takes down the caller.

def create_notification(
    org_id: str,
    kind: str,
    title: str,
    *,
    body: str = "",
    severity: str = "info",
    audience: str = "all",
    link: Optional[str] = None,
    camera_id: Optional[str] = None,
    node_id: Optional[str] = None,
    meta: Optional[dict] = None,
    db: Optional[Session] = None,
) -> Optional[Notification]:
    """Persist a notification and broadcast it to subscribers.

    Pass ``db`` to reuse an existing session (recommended when called
    from inside a request handler that already has one); otherwise a
    fresh SessionLocal is opened and closed here.
    Returns the saved Notification or None on failure.
    """
    owns_session = db is None
    session = db or SessionLocal()

    if audience not in ("all", "admin"):
        audience = "all"
    if severity not in ("info", "warning", "error", "critical"):
        severity = "info"

    try:
        notif = Notification(
            org_id=org_id,
            kind=kind,
            audience=audience,
            title=title[:200],
            body=body or "",
            severity=severity,
            link=link,
            camera_id=camera_id,
            node_id=node_id,
            meta_json=json.dumps(meta) if meta else None,
        )
        session.add(notif)
        session.commit()
        session.refresh(notif)

        # Broadcast after commit so subscribers never see a row that
        # could later be rolled back.
        payload = notif.to_dict()
        payload["type"] = "notification"
        payload["audience"] = audience
        notification_broadcaster.notify(org_id, payload)
        return notif
    except Exception:
        logger.exception("[Notifications] Failed to create notification")
        try:
            session.rollback()
        except Exception:
            pass
        return None
    finally:
        if owns_session:
            session.close()


# ── Status transitions (online ↔ offline) ─────────────────────────
# Cameras/nodes flap: a node with a spotty uplink can toggle online/
# offline every few seconds.  We debounce per-(entity, direction) so
# the inbox doesn't drown in duplicates.  The debounce is in-memory
# only — acceptable because the worst case after a process restart is
# one extra notification, and notifications are append-only anyway.

_TRANSITION_DEBOUNCE_SECONDS = 60
_transition_debounce: dict[tuple[str, str, str], float] = {}


def _should_emit_transition(kind: str, entity_id: str, direction: str) -> bool:
    """Return True if we haven't emitted this (kind,entity,direction)
    recently.  Updates the timestamp on a positive return so subsequent
    calls within the debounce window are suppressed."""
    key = (kind, entity_id, direction)
    now = _time.monotonic()
    last = _transition_debounce.get(key, 0.0)
    if now - last < _TRANSITION_DEBOUNCE_SECONDS:
        return False
    _transition_debounce[key] = now
    return True


def clear_transition_debounce() -> None:
    """Reset the in-memory debounce map.  Exposed for tests."""
    _transition_debounce.clear()


def emit_camera_transition(
    db: Session,
    *,
    camera_id: str,
    org_id: str,
    display_name: str,
    new_status: str,
    node_id: Optional[str] = None,
) -> Optional[Notification]:
    """Emit a camera online↔offline transition notification.

    Audience is ``"all"`` — every org member cares when a camera drops.
    Debounced per-(camera, direction) to survive flaps.
    """
    if new_status not in ("online", "offline"):
        return None
    if not _should_emit_transition("camera", camera_id, new_status):
        return None

    if new_status == "online":
        return create_notification(
            org_id=org_id,
            kind="camera_online",
            title=f"{display_name} is online",
            body="Camera is streaming again.",
            severity="info",
            audience="all",
            link=f"/dashboard?camera={camera_id}",
            camera_id=camera_id,
            node_id=node_id,
            db=db,
        )
    return create_notification(
        org_id=org_id,
        kind="camera_offline",
        title=f"{display_name} went offline",
        body="No heartbeat received in over 90 seconds.",
        severity="warning",
        audience="all",
        link=f"/dashboard?camera={camera_id}",
        camera_id=camera_id,
        node_id=node_id,
        db=db,
    )


def emit_node_transition(
    db: Session,
    *,
    node_id: str,
    org_id: str,
    display_name: str,
    new_status: str,
) -> Optional[Notification]:
    """Emit a node online↔offline transition notification.

    Audience is ``"admin"`` — node health is an operator concern; regular
    viewers don't need to know about CloudNode uplink status.
    """
    if new_status not in ("online", "offline"):
        return None
    if not _should_emit_transition("node", node_id, new_status):
        return None

    if new_status == "online":
        return create_notification(
            org_id=org_id,
            kind="node_online",
            title=f"Node '{display_name}' is online",
            body="CloudNode is connected and reporting.",
            severity="info",
            audience="admin",
            link="/admin",
            node_id=node_id,
            db=db,
        )
    return create_notification(
        org_id=org_id,
        kind="node_offline",
        title=f"Node '{display_name}' went offline",
        body="No heartbeat received in over 90 seconds.",
        severity="warning",
        audience="admin",
        link="/admin",
        node_id=node_id,
        db=db,
    )


# ── Read-state helpers ─────────────────────────────────────────────

def _get_or_init_state(
    db: Session, clerk_user_id: str, org_id: str
) -> UserNotificationState:
    """Return the user's read-state row, creating it on first access.

    First-time users see every existing notification as "unread" would be
    noisy, so we initialise last_viewed_at to NOW on creation — meaning a
    brand new user only sees notifications that arrive after they first
    load the app.
    """
    state = (
        db.query(UserNotificationState)
        .filter_by(clerk_user_id=clerk_user_id, org_id=org_id)
        .first()
    )
    if state is None:
        state = UserNotificationState(
            clerk_user_id=clerk_user_id,
            org_id=org_id,
            last_viewed_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _audience_filter_clause(user: AuthUser):
    """SQLAlchemy filter that hides admin-only notifications from non-admins."""
    if user.is_admin:
        return None  # admins see everything
    return Notification.audience == "all"


# ── Routes ─────────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    limit: int = Query(default=50, le=200, ge=1),
    offset: int = Query(default=0, ge=0),
    hours: int = Query(default=168, le=720),  # default 7 days, max 30 days
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Paginated inbox for the current user, newest first.

    Non-admins never see ``audience="admin"`` rows.  Read-state is
    reported per-item (based on last_viewed_at) so the UI can render
    the unread ones differently without another round trip.
    """
    since = datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    query = db.query(Notification).filter(
        Notification.org_id == user.org_id,
        Notification.created_at >= since,
    )

    aud_clause = _audience_filter_clause(user)
    if aud_clause is not None:
        query = query.filter(aud_clause)

    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    state = _get_or_init_state(db, user.user_id, user.org_id)
    last_viewed = state.last_viewed_at

    items = []
    for n in rows:
        d = n.to_dict()
        d["unread"] = bool(last_viewed is None or (n.created_at and n.created_at > last_viewed))
        items.append(d)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "last_viewed_at": last_viewed.isoformat() if last_viewed else None,
        "notifications": items,
    }


@router.get("/unread-count")
async def unread_count(
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Cheap count for the bell badge. Cap at 99 for display sanity."""
    state = _get_or_init_state(db, user.user_id, user.org_id)

    query = db.query(Notification).filter(
        Notification.org_id == user.org_id,
        Notification.created_at > state.last_viewed_at,
    )
    aud_clause = _audience_filter_clause(user)
    if aud_clause is not None:
        query = query.filter(aud_clause)

    count = query.count()
    return {
        "unread": count,
        "capped": count > 99,
        "last_viewed_at": state.last_viewed_at.isoformat() if state.last_viewed_at else None,
    }


@router.post("/mark-viewed")
async def mark_viewed(
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Bump the user's last_viewed_at to now, clearing the unread badge."""
    state = _get_or_init_state(db, user.user_id, user.org_id)
    state.last_viewed_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.commit()
    return {
        "success": True,
        "last_viewed_at": state.last_viewed_at.isoformat(),
    }


@router.get("/stream")
async def stream_notifications(user: AuthUser = Depends(require_view)):
    """SSE — streams new notifications to the bell panel in real time.

    The audience filter is applied at broadcast time (see
    NotificationBroadcaster.notify) so non-admins never even receive
    admin-only events on the wire.
    """
    org_id = user.org_id
    is_admin = user.is_admin
    queue = notification_broadcaster.subscribe(org_id, is_admin)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'org_id': org_id})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            notification_broadcaster.unsubscribe(org_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
