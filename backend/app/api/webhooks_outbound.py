"""
Outbound webhooks — Pro Plus feature that pushes events to customer-controlled
HTTPS endpoints the moment they happen, instead of making customers poll the
REST API or keep a long-lived MCP session open.

Event flow:
  1. Something interesting happens in the backend (motion detected, camera
     flipped offline, etc.) and the producing code calls
     ``dispatch_event(db, org_id, kind, payload)``.
  2. ``dispatch_event`` looks up every enabled ``WebhookEndpoint`` for the
     org whose ``events`` filter matches ``kind`` and schedules one delivery
     task per endpoint via ``asyncio.create_task``.
  3. The delivery task signs the body, POSTs it, records the result in the
     endpoint row, and retries with exponential backoff on 5xx/network
     errors up to 3 times. 4xx responses are NOT retried — the caller's
     endpoint told us it didn't want the event, retrying won't change that.
  4. Consecutive failures are tracked on the row; after 20 in a row we
     auto-disable the endpoint so a dead customer URL doesn't burn our
     outbound network budget forever.

Security:
  - HTTPS-only. ``http://`` URLs are rejected at create time so we never
    ship customer data over plaintext.
  - HMAC-SHA256 of the raw body, hex-encoded, shipped in
    ``X-SourceBox-Signature``. The receiving endpoint verifies with the
    ``signing_secret`` returned once at create time.
  - Signing secret is plaintext in the DB (we need it to sign; there's no
    way to re-derive from a hash). Treat it as a credential — never log it,
    never include in list/get responses, show-once on create.

This is a Pro Plus-only feature. The gating lives on the router's
``require_admin`` + an explicit plan check in each mutating handler.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_admin
from app.core.database import SessionLocal, get_db
from app.core.limiter import limiter
from app.models.models import WebhookEndpoint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks-outbound", tags=["webhooks-outbound"])


# Plan slugs that unlock outbound webhooks. "business" is the transitional
# alias the backend keeps for the pre-rename Clerk slug; see plans.py.
PRO_PLUS_SLUGS = frozenset({"pro_plus", "business"})


def _plan_allowed(plan: str) -> bool:
    """Only Pro Plus (and the pre-rename alias) gets outbound webhooks."""
    return plan in PRO_PLUS_SLUGS


# Auto-disable threshold. Once an endpoint has failed this many times in a
# row we flip ``enabled=False`` so a dead URL doesn't burn outbound
# connections forever. The admin can re-enable from the settings page
# after they fix their endpoint.
MAX_CONSECUTIVE_FAILURES = 20

# Per-attempt timeout. Long enough for cold-started Lambda endpoints to
# respond; short enough that a hung customer endpoint doesn't keep us
# tied up.
DELIVERY_TIMEOUT_SECONDS = 10.0

# Retry backoff — index = attempt number (0 = first try).
RETRY_BACKOFF_SECONDS = [0, 1.0, 5.0, 30.0]


# ── CRUD schemas ────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., max_length=500)
    events: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _must_be_https(cls, v: str) -> str:
        # Reject ``http://`` so we never POST signed events in plaintext.
        # The signing header doesn't protect confidentiality — an attacker
        # on the wire reads the full body. TLS is non-negotiable.
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must start with https://")
        if len(v) < 10:
            raise ValueError("Webhook URL looks malformed")
        return v

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, v: list[str]) -> list[str]:
        # Empty list ⇒ subscribe to all events. Otherwise every item must
        # match a known event kind; stray strings would silently never
        # fire, which is confusing.
        valid = {"motion", "camera_online", "camera_offline", "node_online", "node_offline"}
        cleaned = [e.strip() for e in v if e.strip()]
        bad = [e for e in cleaned if e not in valid]
        if bad:
            raise ValueError(
                f"Unknown event types: {bad}. "
                f"Valid: {sorted(valid)}"
            )
        return cleaned


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, max_length=500)
    events: Optional[list[str]] = None
    enabled: Optional[bool] = None

    @field_validator("url")
    @classmethod
    def _must_be_https(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must start with https://")
        return v

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return WebhookCreate._normalize_events(v)


# ── Routes ──────────────────────────────────────────────────────────────

@router.get("")
async def list_webhooks(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List this org's outbound webhook endpoints. Free/Pro orgs get an
    empty list plus an ``upgrade_required=True`` hint so the settings UI
    can show the right pitch rather than pretend the feature doesn't
    exist."""
    if not _plan_allowed(user.plan):
        return {"endpoints": [], "upgrade_required": True, "feature": "outbound_webhooks"}

    rows = (
        db.query(WebhookEndpoint)
        .filter_by(org_id=user.org_id)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return {"endpoints": [r.to_dict() for r in rows], "upgrade_required": False}


@router.post("")
@limiter.limit("30/hour")
async def create_webhook(
    request: Request,
    data: WebhookCreate,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new webhook endpoint. Returns the signing secret exactly
    once — the caller must store it immediately to validate incoming
    deliveries."""
    if not _plan_allowed(user.plan):
        raise HTTPException(
            status_code=403,
            detail="Outbound webhooks require the Pro Plus plan. Upgrade at /pricing.",
        )

    # A hard cap on endpoints per org keeps the per-event delivery fan-out
    # bounded no matter how many URLs a customer plugs in. 20 is more than
    # any reasonable ops setup needs; beyond that they should be using a
    # single forwarder (Zapier/n8n) in front of their own services.
    count = db.query(WebhookEndpoint).filter_by(org_id=user.org_id).count()
    if count >= 20:
        raise HTTPException(
            status_code=403,
            detail="Webhook endpoint cap reached (20 per org). Delete unused endpoints first.",
        )

    # 32 bytes ⇒ 64-char hex secret. More than enough entropy to make
    # brute-forcing the HMAC infeasible.
    secret = secrets.token_hex(32)

    endpoint = WebhookEndpoint(
        org_id=user.org_id,
        name=data.name,
        url=data.url,
        signing_secret=secret,
        events=",".join(data.events),
        enabled=True,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    logger.info("Webhook endpoint created: org=%s name=%s url=%s", user.org_id, data.name, data.url)

    # include_secret=True only on the create-time response. List/get responses
    # never leak it again.
    return endpoint.to_dict(include_secret=True)


@router.patch("/{endpoint_id}")
@limiter.limit("60/minute")
async def update_webhook(
    request: Request,
    endpoint_id: int,
    data: WebhookUpdate,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Toggle enabled, rename, or re-target an endpoint. The signing
    secret is not rotated here — if a customer suspects a leak they
    should delete + re-create to get a fresh secret."""
    if not _plan_allowed(user.plan):
        raise HTTPException(
            status_code=403,
            detail="Outbound webhooks require the Pro Plus plan.",
        )

    endpoint = (
        db.query(WebhookEndpoint)
        .filter_by(id=endpoint_id, org_id=user.org_id)
        .first()
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if data.name is not None:
        endpoint.name = data.name
    if data.url is not None:
        endpoint.url = data.url
    if data.events is not None:
        endpoint.events = ",".join(data.events)
    if data.enabled is not None:
        endpoint.enabled = data.enabled
        if data.enabled:
            # Clearing the failure counter on manual re-enable so a
            # fixed endpoint isn't auto-disabled on the next hiccup.
            endpoint.consecutive_failures = 0
    db.commit()
    db.refresh(endpoint)
    return endpoint.to_dict()


@router.delete("/{endpoint_id}")
@limiter.limit("30/minute")
async def delete_webhook(
    request: Request,
    endpoint_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete an endpoint. No grace period — customers who
    want to pause deliveries should toggle ``enabled=false`` instead."""
    if not _plan_allowed(user.plan):
        raise HTTPException(
            status_code=403,
            detail="Outbound webhooks require the Pro Plus plan.",
        )

    endpoint = (
        db.query(WebhookEndpoint)
        .filter_by(id=endpoint_id, org_id=user.org_id)
        .first()
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(endpoint)
    db.commit()
    return {"success": True}


@router.post("/{endpoint_id}/test")
@limiter.limit("10/minute")
async def test_webhook(
    request: Request,
    endpoint_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Fire a synthetic ``test`` event at the endpoint so the customer
    can verify their receiver is wired up correctly before waiting for
    a real motion event."""
    if not _plan_allowed(user.plan):
        raise HTTPException(
            status_code=403,
            detail="Outbound webhooks require the Pro Plus plan.",
        )

    endpoint = (
        db.query(WebhookEndpoint)
        .filter_by(id=endpoint_id, org_id=user.org_id)
        .first()
    )
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")

    payload = {
        "event": "test",
        "org_id": user.org_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "message": "This is a test event from SourceBox Sentry.",
    }
    asyncio.create_task(_deliver(endpoint.id, "test", payload))
    return {"success": True, "scheduled": True}


# ── Dispatch + delivery ─────────────────────────────────────────────────

def _sign(body: bytes, secret: str) -> str:
    """HMAC-SHA256, hex-encoded. The receiving endpoint runs the same
    computation against the raw request body and compares constant-time."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _matches_filter(events_csv: str, kind: str) -> bool:
    """Empty filter means "subscribe to everything"; otherwise the event
    kind must appear in the comma-separated whitelist."""
    if not events_csv.strip():
        return True
    return kind in {e.strip() for e in events_csv.split(",") if e.strip()}


def dispatch_event(db: Session, org_id: str, kind: str, payload: dict) -> int:
    """Schedule outbound delivery of an event to every matching endpoint.

    Called from within the producing code's DB session (ws.py for motion,
    notifications.py for transitions, etc.). Looks up matching endpoints,
    spawns one fire-and-forget async task per delivery. The session the
    caller passes is used only for the lookup — the delivery tasks open
    their own sessions because they outlive the request.

    Returns the number of endpoints we scheduled deliveries for; callers
    can log this for visibility. Zero endpoints (or all filtered out) is
    a happy no-op.
    """
    try:
        rows = (
            db.query(WebhookEndpoint)
            .filter_by(org_id=org_id, enabled=True)
            .all()
        )
    except Exception:
        logger.exception("[Webhooks] endpoint lookup failed for org %s", org_id)
        return 0

    body = {
        "event": kind,
        "org_id": org_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "data": payload,
    }

    scheduled = 0
    for row in rows:
        if not _matches_filter(row.events or "", kind):
            continue
        try:
            asyncio.get_event_loop().create_task(_deliver(row.id, kind, body))
            scheduled += 1
        except RuntimeError:
            # No running event loop — shouldn't happen inside the FastAPI
            # worker, but be defensive. Log and skip; the next event will
            # fire normally.
            logger.warning("[Webhooks] no running loop to schedule delivery to %d", row.id)
    return scheduled


async def _deliver(endpoint_id: int, kind: str, payload: dict) -> None:
    """Deliver ``payload`` to ``endpoint_id`` with retries. Self-contained —
    opens its own DB session for the endpoint lookup and status updates
    because the original request has long since returned by the time later
    retries fire.

    Deletions in-flight are tolerated: if the endpoint is gone by the
    time we look it up, we silently stop retrying.
    """
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    # Re-read the row inside each attempt so a rotation / disable between
    # retries actually takes effect.
    for attempt, backoff in enumerate(RETRY_BACKOFF_SECONDS):
        if backoff > 0:
            await asyncio.sleep(backoff)

        db = SessionLocal()
        try:
            endpoint = db.query(WebhookEndpoint).filter_by(id=endpoint_id).first()
            if not endpoint or not endpoint.enabled:
                return  # endpoint deleted or disabled — stop retrying

            signature = _sign(body, endpoint.signing_secret)
            target_url = endpoint.url
        finally:
            db.close()

        status_code: int | None = None
        error_detail: str | None = None
        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    target_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "SourceBox-Sentry-Webhooks/1",
                        "X-SourceBox-Event": kind,
                        "X-SourceBox-Signature": signature,
                        "X-SourceBox-Delivery-Attempt": str(attempt + 1),
                    },
                )
            status_code = resp.status_code
            if 200 <= status_code < 300:
                # Success — record and stop retrying.
                _record_delivery(endpoint_id, status_code, None, success=True)
                return
            # 4xx: the receiver rejected this event; retrying won't change
            # their mind. 5xx: transient — keep retrying.
            if 400 <= status_code < 500:
                error_detail = f"HTTP {status_code} (not retried)"
                _record_delivery(endpoint_id, status_code, error_detail, success=False)
                return
            error_detail = f"HTTP {status_code}"
        except httpx.TimeoutException:
            error_detail = f"timeout after {DELIVERY_TIMEOUT_SECONDS}s"
        except httpx.RequestError as e:
            # Network error — DNS, connect refused, TLS handshake failure.
            error_detail = f"network error: {type(e).__name__}: {e}"[:500]
        except Exception as e:
            # Defensive: unknown error shouldn't silently lose the event,
            # but it also shouldn't crash the delivery loop.
            error_detail = f"unexpected error: {type(e).__name__}: {e}"[:500]
            logger.exception("[Webhooks] unexpected delivery error to endpoint %d", endpoint_id)

        # Record the failure; the next loop iteration (if any) will retry.
        _record_delivery(endpoint_id, status_code or 0, error_detail, success=False)

    # All retries exhausted.
    logger.warning(
        "[Webhooks] endpoint %d exhausted %d retries for event %s",
        endpoint_id, len(RETRY_BACKOFF_SECONDS), kind,
    )


def _record_delivery(
    endpoint_id: int,
    status_code: int,
    error: str | None,
    *,
    success: bool,
) -> None:
    """Update the endpoint row with the last delivery result. Also handles
    auto-disable once ``consecutive_failures`` crosses ``MAX_CONSECUTIVE_FAILURES``.
    Failure to persist is logged but never propagated — we don't want a
    DB hiccup to leak as an exception into the delivery task."""
    db = SessionLocal()
    try:
        endpoint = db.query(WebhookEndpoint).filter_by(id=endpoint_id).first()
        if not endpoint:
            return
        endpoint.last_delivery_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        endpoint.last_delivery_status = status_code if status_code else None
        endpoint.last_delivery_error = error
        if success:
            endpoint.consecutive_failures = 0
        else:
            endpoint.consecutive_failures = (endpoint.consecutive_failures or 0) + 1
            if endpoint.consecutive_failures >= MAX_CONSECUTIVE_FAILURES and endpoint.enabled:
                endpoint.enabled = False
                logger.warning(
                    "[Webhooks] auto-disabled endpoint %d after %d consecutive failures",
                    endpoint_id, endpoint.consecutive_failures,
                )
        db.commit()
    except Exception:
        logger.exception("[Webhooks] failed to record delivery status for %d", endpoint_id)
        db.rollback()
    finally:
        db.close()
