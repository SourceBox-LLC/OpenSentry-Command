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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.auth import AuthUser, require_admin, require_view
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.email_unsubscribe import verify_token
from app.core.limiter import limiter
from app.core.recipients import get_recipient_emails
from app.models.models import EmailOutbox, EmailSuppression, Notification, Setting, UserNotificationState


# ── Per-org preference gate ────────────────────────────────────────
# Which notification kinds the org wants delivered to the inbox.
# Defaults intentionally match "everything on" so behaviour before the
# settings UI shipped is unchanged — operators only ever see less noise
# than before, never more.  Keys map kind → (setting_key, default).

_NOTIFICATION_KIND_TO_SETTING: dict[str, tuple[str, bool]] = {
    "motion": ("motion_notifications", True),
    "camera_online": ("camera_transition_notifications", True),
    "camera_offline": ("camera_transition_notifications", True),
    "node_online": ("node_transition_notifications", True),
    "node_offline": ("node_transition_notifications", True),
}


# ── Email side-channel preference gate ─────────────────────────────
# Per-org per-kind "should we email this notification?" toggle.  The
# inbox gate above (_NOTIFICATION_KIND_TO_SETTING) decides whether
# the notification appears in the bell-icon panel; this map decides
# whether it ALSO emails out.
#
# Different defaults from the inbox gate on purpose:
#   - The "online" recovery events are NOT emailed even when the
#     "offline" events are — recovery is good news that doesn't need
#     a midnight email.  Keeps the inbox feed and the email feed
#     intentionally different shapes.
#   - Motion is omitted entirely from this map for v1.  Adding it
#     before the digest/cooldown work in v1.1 is the difference
#     between "useful" and "unsubscribed within an hour."
#   - All other defaults are True so an org that hasn't visited the
#     settings page still gets the operator-critical alerts.
#
# When EMAIL_ENABLED is False globally (the kill-switch), this gate
# is bypassed entirely and no rows get enqueued — we don't enqueue
# rows just to have the worker discard them.
_EMAIL_KIND_TO_SETTING: dict[str, tuple[str, bool]] = {
    "camera_offline":   ("email_camera_offline",   True),
    "node_offline":     ("email_node_offline",     True),
    "disk_critical":    ("email_disk_critical",    True),
    "incident_created": ("email_incident_created", True),
}


def notifications_enabled(db: Session, org_id: str, kind: str) -> bool:
    """Return True if notifications of ``kind`` should be delivered for
    ``org_id``.  Unknown kinds default to enabled so new notification
    types don't silently disappear when added without a settings migration.

    Reads from the ``Setting`` table using the same "string value" pattern
    the recording toggles use.  Keeping it here (not in the motion path)
    means every emitter can gate without duplicating the lookup logic.
    """
    cfg = _NOTIFICATION_KIND_TO_SETTING.get(kind)
    if cfg is None:
        return True
    key, default = cfg
    val = Setting.get(db, org_id, key, None)
    if val is None:
        return default
    return val == "true"


def email_enabled_for_kind(db: Session, org_id: str, kind: str) -> bool:
    """Return True if this org wants ``kind`` notifications emailed out.

    Two gates in series:
      1. ``settings.EMAIL_ENABLED`` — global kill-switch.  If False, no
         org gets emails regardless of their per-kind preference.
      2. Per-org per-kind setting in the ``Setting`` table.  Defaults
         from ``_EMAIL_KIND_TO_SETTING`` apply when the row is absent.

    Unknown kinds return False — the inbox gate defaults unknown kinds
    to ENABLED for forward-compat, but the email gate is the opposite:
    we'd rather miss emailing a brand-new kind than blast users on it
    by default before the per-kind setting UI catches up.
    """
    if not settings.EMAIL_ENABLED:
        return False
    cfg = _EMAIL_KIND_TO_SETTING.get(kind)
    if cfg is None:
        return False
    key, default = cfg
    val = Setting.get(db, org_id, key, None)
    if val is None:
        return default
    return val == "true"


def _build_email_content(notif: Notification) -> tuple[str, str, str]:
    """Render a notification into ``(subject, body_text, body_html)``
    via the Jinja2 templates in ``app/templates/emails/``.

    Thin wrapper around ``app.core.email_templates.render`` — the
    interesting work lives there.  This wrapper exists so callers in
    ``create_notification()`` don't need to know about the
    unsubscribe-token path, the dashboard URL config, or the
    template module's import shape.
    """
    from app.core import email_templates
    from app.core.email_unsubscribe import build_unsubscribe_url

    unsubscribe_url = build_unsubscribe_url(notif.org_id, notif.kind)
    return email_templates.render(
        notif.kind,
        notif,
        unsubscribe_url=unsubscribe_url,
    )


def _enqueue_email_for_notification(
    session: Session, notif: Notification, audience: str
) -> int:
    """Look up recipients and insert one EmailOutbox row per address.

    Returns the count of rows enqueued (zero on any failure).  Never
    raises — this is called from inside ``create_notification`` and a
    failure here must not roll back the inbox notification we just
    committed.

    Caller must have already verified ``email_enabled_for_kind()`` is
    True; this function unconditionally enqueues for the audience.
    """
    try:
        recipients = get_recipient_emails(notif.org_id, audience)
    except Exception:
        logger.exception(
            "[Notifications] recipient lookup failed for org=%s kind=%s",
            notif.org_id, notif.kind,
        )
        return 0

    if not recipients:
        return 0

    try:
        subject, body_text, body_html = _build_email_content(notif)
    except Exception:
        logger.exception(
            "[Notifications] email template render failed for kind=%s",
            notif.kind,
        )
        return 0

    enqueued = 0
    for addr in recipients:
        try:
            session.add(EmailOutbox(
                org_id=notif.org_id,
                recipient_email=addr,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                kind=notif.kind,
                notification_id=notif.id,
                status="pending",
            ))
            enqueued += 1
        except Exception:
            logger.exception(
                "[Notifications] enqueue failed for org=%s kind=%s addr=%s",
                notif.org_id, notif.kind, addr,
            )

    if enqueued:
        try:
            session.commit()
        except Exception:
            logger.exception(
                "[Notifications] outbox commit failed for kind=%s", notif.kind,
            )
            try:
                session.rollback()
            except Exception:
                pass
            return 0

    return enqueued

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── Broadcaster ─────────────────────────────────────────────────────
# Same pattern as motion_broadcaster — one asyncio.Queue per SSE
# subscriber, scoped by org.  Each event also carries the audience so
# the stream generator can filter per subscriber.

# Per-org SSE subscriber cap. Tiered — see the matching comment in motion.py.
# This module-level constant is the fallback; route handlers pass the
# plan-specific cap from ``app.core.plans.PLAN_LIMITS``.
MAX_SSE_SUBSCRIBERS_PER_ORG = 100  # fallback — Pro Plus default


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

    def subscribe(
        self,
        org_id: str,
        is_admin: bool,
        cap: int = MAX_SSE_SUBSCRIBERS_PER_ORG,
    ) -> Optional[asyncio.Queue]:
        """Add a new SSE subscription for an org.

        ``cap`` is the per-tier subscriber cap the caller looked up (see
        PLAN_LIMITS). Returns the queue on success, or ``None`` when this
        org is already at the cap — the route handler translates that into
        a 429.
        """
        existing = self._subscribers.setdefault(org_id, [])
        if len(existing) >= cap:
            logger.warning(
                "[Notifications] SSE cap hit for org %s (%d/%d) — rejecting",
                org_id, len(existing), cap,
            )
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        existing.append((q, is_admin))
        logger.info(
            "[Notifications] SSE subscriber added for org %s (admin=%s, %d/%d)",
            org_id, is_admin, len(existing), cap,
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

    # Per-org preference gate — an operator who turned off "motion
    # notifications" in Settings should stop seeing new motion rows in
    # the inbox without affecting the motion-event pipeline itself.
    # Done here (vs. at each call site) so every emitter, current and
    # future, automatically respects the toggle.
    try:
        if not notifications_enabled(session, org_id, kind):
            return None
    except Exception:
        # Gate failures must not block notifications — fall through to
        # the normal create path so we're no worse off than before the
        # gate existed.
        logger.exception("[Notifications] preference lookup failed; emitting anyway")

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

        # Email side-channel.  Same gate pattern as the inbox
        # preference, different setting key.  Failure never blocks
        # the caller — the inbox notification is already committed
        # and a missing email is recoverable (operator can re-trigger
        # the alert), but a failure that propagated out of here
        # would prevent the notification from showing up in the
        # bell panel too.
        try:
            if email_enabled_for_kind(session, org_id, kind):
                _enqueue_email_for_notification(session, notif, audience)
        except Exception:
            logger.exception(
                "[Notifications] email enqueue side-channel failed for kind=%s",
                kind,
            )

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
    calls within the debounce window are suppressed.

    The sentinel for "never emitted before" is ``-inf``, not ``0.0`` —
    otherwise on a freshly-booted host (e.g. GitHub Actions runners,
    where ``time.monotonic()`` starts near zero) the very first emit
    can fall inside the debounce window and get silently dropped.
    """
    key = (kind, entity_id, direction)
    now = _time.monotonic()
    last = _transition_debounce.get(key, float("-inf"))
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

    kind = "camera_online" if new_status == "online" else "camera_offline"
    return create_notification(
        org_id=org_id,
        kind=kind,
        title=f"{display_name} is online" if new_status == "online" else f"{display_name} went offline",
        body="Camera is streaming again." if new_status == "online" else "No heartbeat received in over 90 seconds.",
        severity="info" if new_status == "online" else "warning",
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

    kind = "node_online" if new_status == "online" else "node_offline"
    return create_notification(
        org_id=org_id,
        kind=kind,
        title=f"Node '{display_name}' is online" if new_status == "online" else f"Node '{display_name}' went offline",
        body="CloudNode is connected and reporting." if new_status == "online" else "No heartbeat received in over 90 seconds.",
        severity="info" if new_status == "online" else "warning",
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
    # OFFSET is O(n) — cap so no one can force SQLite to skip billions.
    offset: int = Query(default=0, ge=0, le=1_000_000),
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

    # Initialise read-state first so we know the user's cleared_at
    # threshold before building the query.  Cleared notifications are
    # filtered out here (not hard-deleted) so other users in the same
    # org still see them and audit queries still see every row.
    state = _get_or_init_state(db, user.user_id, user.org_id)
    last_viewed = state.last_viewed_at
    cleared_at = state.cleared_at

    query = db.query(Notification).filter(
        Notification.org_id == user.org_id,
        Notification.created_at >= since,
    )
    if cleared_at is not None:
        query = query.filter(Notification.created_at > cleared_at)

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


@router.post("/clear-all")
async def clear_all(
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Hide every currently-visible notification from this user's inbox.

    Stamps both ``cleared_at`` (list filter) and ``last_viewed_at``
    (unread count) to "now" so the panel becomes empty and the badge
    drops to zero in a single round trip.  Nothing is deleted —
    notifications remain in the DB for audit, incidents, and for
    other users in the same org who haven't cleared.  Anything
    created after this call reappears normally.
    """
    state = _get_or_init_state(db, user.user_id, user.org_id)
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    state.cleared_at = now
    state.last_viewed_at = now
    db.commit()
    return {
        "success": True,
        "cleared_at": state.cleared_at.isoformat(),
        "last_viewed_at": state.last_viewed_at.isoformat(),
    }


@router.get("/stream")
async def stream_notifications(user: AuthUser = Depends(require_view)):
    """SSE — streams new notifications to the bell panel in real time.

    The audience filter is applied at broadcast time (see
    NotificationBroadcaster.notify) so non-admins never even receive
    admin-only events on the wire.
    """
    from app.core.plans import get_plan_limits
    org_id = user.org_id
    is_admin = user.is_admin
    cap = get_plan_limits(user.plan).get("max_sse_subscribers", MAX_SSE_SUBSCRIBERS_PER_ORG)
    queue = notification_broadcaster.subscribe(org_id, is_admin, cap)
    if queue is None:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many open notification streams for this org (cap: "
                f"{cap} on your current plan). Close unused tabs and retry, "
                f"or upgrade for a higher cap."
            ),
        )

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


# ── Email preferences ──────────────────────────────────────────────
# Per-org per-kind toggles for the email side-channel.  GET is
# require_view (anyone in the org can SEE current prefs); POST is
# require_admin + audit (only admins can change them).
#
# The shape returned matches the keys in _EMAIL_KIND_TO_SETTING — a
# stable contract for the frontend toggle UI.  Adding a new kind
# means: add to _EMAIL_KIND_TO_SETTING, add a template, add a
# checkbox to the frontend.  No API change.


class EmailPreferences(BaseModel):
    """Request body for POST /email/preferences.

    Each field is optional — clients only send the toggles they're
    actually changing.  Unset fields keep their existing values.
    """
    email_camera_offline: Optional[bool] = None
    email_node_offline: Optional[bool] = None
    email_disk_critical: Optional[bool] = None
    email_incident_created: Optional[bool] = None


def _current_email_prefs(db: Session, org_id: str) -> dict:
    """Return the org's effective email prefs as a {key: bool} dict.

    Reads each setting; falls back to the per-kind default in
    ``_EMAIL_KIND_TO_SETTING`` when the row is absent.  This is
    what the frontend toggle UI shows on first load — the absence
    of a Setting row is presented as the default ON state, not a
    blank "unset" state.
    """
    out = {}
    for kind, (key, default) in _EMAIL_KIND_TO_SETTING.items():
        val = Setting.get(db, org_id, key, None)
        if val is None:
            out[key] = default
        else:
            out[key] = (val == "true")
    return out


@router.get("/email/preferences")
async def get_email_preferences(
    user: AuthUser = Depends(require_view),
    db: Session = Depends(get_db),
):
    """Return the current per-kind email toggles for the org.

    Includes ``email_globally_enabled`` flag derived from
    ``settings.EMAIL_ENABLED`` so the frontend can show "emails are
    currently turned off at the platform level" copy alongside
    individually-still-enabled toggles.  This is the difference
    between the operator's kill-switch and the org's prefs — the UI
    needs both signals to render the right state.
    """
    return {
        "email_globally_enabled": settings.EMAIL_ENABLED,
        "preferences": _current_email_prefs(db, user.org_id),
    }


@router.post("/email/preferences")
async def update_email_preferences(
    request: Request,
    prefs: EmailPreferences,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update the org's per-kind email toggles.

    Only fields present in the request body are touched — partial
    updates are the norm (frontend toggles fire one at a time).
    Audit row written for every change so admin actions are
    traceable.

    Returns the updated full pref dict so the frontend doesn't need
    a follow-up GET to reflect the new state.
    """
    changes = []
    for key, value in prefs.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        # Validate the key is one we recognise.  Pydantic already
        # restricts the field set, but defense in depth — if a
        # future field gets added without a corresponding
        # _EMAIL_KIND_TO_SETTING entry, this rejects it cleanly.
        if not any(cfg[0] == key for cfg in _EMAIL_KIND_TO_SETTING.values()):
            continue
        Setting.set(db, user.org_id, key, "true" if value else "false")
        changes.append(f"{key}={value}")

    if changes:
        write_audit(
            db,
            org_id=user.org_id,
            event="email_prefs_updated",
            user_id=user.user_id,
            username=user.email or user.username,
            details=", ".join(changes),
            request=request,
        )

    return {
        "email_globally_enabled": settings.EMAIL_ENABLED,
        "preferences": _current_email_prefs(db, user.org_id),
        "changes": changes,
    }


# ── Unsubscribe ────────────────────────────────────────────────────
# Public endpoint, no auth required — the JWT in the URL is the
# auth.  Rate-limited via the global slowapi middleware (every route
# is bounded by ``tenant_aware_key`` + the default per-IP cap) so a
# stream of bad tokens can't burn the DB.
#
# Returns HTML (not JSON) because this is end-user facing — the
# user clicked a link in their email, they expect a web page, not
# a 200 OK with `{"status": "unsubscribed"}`.

_UNSUBSCRIBE_HTML_OK = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Unsubscribed</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 540px;
         margin: 80px auto; padding: 0 24px; color: #111; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 12px; }}
  p {{ color: #555; }}
  .ok {{ color: #16a34a; font-weight: 600; }}
  a {{ color: #22c55e; }}
</style></head>
<body>
  <h1><span class="ok">✓</span> You're unsubscribed</h1>
  <p>We won't email you about <strong>{kind}</strong> alerts anymore.</p>
  <p>You can re-enable this (or fine-tune any other email type) any time
     in your <a href="{frontend}/settings#settings-notifications">notification settings</a>.</p>
</body></html>"""

_UNSUBSCRIBE_HTML_ERROR = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Link expired</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 540px;
         margin: 80px auto; padding: 0 24px; color: #111; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 12px; }}
  p {{ color: #555; }}
  a {{ color: #22c55e; }}
</style></head>
<body>
  <h1>Link not recognised</h1>
  <p>This unsubscribe link looks invalid or has been superseded.
     Sign in to your <a href="{frontend}/settings#settings-notifications">
     notification settings</a> to manage email alerts directly.</p>
</body></html>"""


@router.get("/email/unsubscribe", response_class=HTMLResponse)
@limiter.limit("60/minute")
async def email_unsubscribe(
    request: Request,
    t: str = Query(..., description="Signed unsubscribe token"),
    db: Session = Depends(get_db),
):
    """Process an unsubscribe link click.

    Verifies the JWT, identifies the (org_id, kind) it was issued
    for, flips the corresponding setting to "false", and renders a
    confirmation HTML page.

    Also writes an EmailSuppression row keyed on the recipient's
    address — wait, we don't know the recipient from the token.
    The token only carries (org_id, kind), which is the right
    granularity: "this org no longer wants this kind of email."
    Per-recipient suppression for cases where one user wants to
    opt out while their org-mates keep receiving them is a v1.1
    feature gated on per-user prefs landing.

    Rate-limited via slowapi.  This endpoint is PUBLIC (no auth —
    the JWT in the URL is the auth) so without an explicit limit,
    one leaked link could be hammered to write Setting + AuditLog
    rows in a tight loop.  60/min per (org_id-from-JWT|client-IP)
    is well above any plausible legitimate use (a user clicks the
    link once, maybe twice if they're confused) but rules out
    burst attacks.  The shared Limiter does NOT apply default
    limits, so explicit @limiter.limit is required here.
    """
    frontend = (settings.FRONTEND_URL or "").rstrip("/")

    decoded = verify_token(t)
    if decoded is None:
        return HTMLResponse(
            _UNSUBSCRIBE_HTML_ERROR.format(frontend=frontend),
            status_code=400,
        )

    org_id, kind = decoded

    # Validate the kind is one we know about.  A token signed for a
    # kind we since removed should still acknowledge gracefully.
    cfg = _EMAIL_KIND_TO_SETTING.get(kind)
    if cfg is None:
        return HTMLResponse(
            _UNSUBSCRIBE_HTML_OK.format(kind=kind, frontend=frontend),
        )

    setting_key, _default = cfg
    try:
        Setting.set(db, org_id, setting_key, "false")
    except Exception:
        logger.exception(
            "[Unsubscribe] failed to update setting org=%s key=%s",
            org_id, setting_key,
        )
        # Don't surface the DB error to the user — they clicked an
        # unsubscribe link, they want to feel unsubscribed.  The
        # link is idempotent; they can click again or use the
        # settings page.

    # Audit (no user_id since this is a public link click).
    try:
        write_audit(
            db, org_id=org_id, event="email_unsubscribed",
            details=f"kind={kind} via_link=true",
        )
    except Exception:
        logger.exception("[Unsubscribe] audit write failed")

    # Pretty-print the kind for the user-facing copy.  "camera_offline"
    # → "camera offline" is friendlier than "email_camera_offline".
    pretty_kind = kind.replace("_", " ")
    return HTMLResponse(
        _UNSUBSCRIBE_HTML_OK.format(kind=pretty_kind, frontend=frontend),
    )
