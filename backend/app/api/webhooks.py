import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.clerk import clerk
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.plans import enforce_camera_cap
from app.models.models import (
    AuditLog,
    CameraGroup,
    CameraNode,
    EmailOutbox,
    EmailSuppression,
    McpActivityLog,
    McpApiKey,
    ProcessedWebhook,
    Setting,
    StreamAccessLog,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Member limits per plan — must match Clerk Dashboard plan keys and
# PLAN_LIMITS.max_seats in app.core.plans. Source of truth is plans.py; this
# dict mirrors it here because the webhook handler calls into Clerk's SDK
# which wants the integer directly. ``business`` kept as a transitional alias.
PLAN_MEMBER_LIMITS = {
    "free_org": 2,
    "pro": 10,
    "pro_plus": 20,
    "business": 20,  # transitional alias — remove after rollover
}

# Paid plan slugs. Seeing a subscription.updated with one of these means the
# payment card is active (Clerk wouldn't mark the subscription live otherwise),
# so we can clear any past-due flag we were holding. Kept local to this module
# rather than imported from plans.py to keep webhook semantics self-contained.
# ``business`` kept as a transitional alias — see PLAN_MEMBER_LIMITS comment.
PAID_PLAN_SLUGS_WEBHOOK = frozenset({"pro", "pro_plus", "business"})


def set_org_member_limit(org_id: str, limit: int):
    """Update the Clerk org's max allowed memberships."""
    try:
        clerk.organizations.update(organization_id=org_id, max_allowed_memberships=limit)
        logger.info("Set org %s member limit to %d", org_id, limit)
    except Exception:
        logger.error("Failed to set member limit for org %s", org_id, exc_info=True)


def get_active_plan_slug(items: list) -> str:
    """Extract the active plan slug from subscription items."""
    for item in items:
        plan = item.get("plan", {})
        if item.get("status") == "active" and plan.get("slug"):
            return plan["slug"]
    return "free_org"


@router.post("/clerk")
@limiter.limit("120/minute")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    headers = dict(request.headers)

    if not settings.CLERK_WEBHOOK_SECRET:
        logger.error("CLERK_WEBHOOK_SECRET not set — cannot verify webhook signatures")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook processing unavailable")

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from None

    event_type = event.get("type")
    data = event.get("data", {})

    # ── Idempotency check ──────────────────────────────────────────
    # Svix retries the same message (same svix-id) on any non-2xx or
    # network failure.  Without this guard, a transient hiccup in our
    # handler causes Clerk to redeliver and we re-run every side
    # effect.  Most ops are upserts so it's mostly benign, but
    # enforce_camera_cap is a read-then-write that can fire duplicate
    # transition notifications, and a future non-idempotent handler
    # added without this guard in mind would silently double-execute.
    #
    # Strategy: process-then-mark.  If the handler raises midway, the
    # row isn't recorded and Svix retries — operations are designed
    # to be safe to re-run, so the eventual consistency wins.  Only
    # an already-recorded msg short-circuits.
    svix_msg_id = headers.get("svix-id")
    if svix_msg_id:
        already = (
            db.query(ProcessedWebhook)
            .filter_by(svix_msg_id=svix_msg_id)
            .first()
        )
        if already:
            logger.info(
                "Webhook %s already processed (event=%s) — skipping",
                svix_msg_id, already.event_type or "?",
            )
            return {"status": "duplicate", "svix_id": svix_msg_id}

    logger.info("Webhook received: %s", event_type)

    # ── Subscription lifecycle ──────────────────────────────────────
    if event_type in ("subscription.created", "subscription.updated", "subscription.active"):
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            plan_slug = get_active_plan_slug(data.get("items", []))
            limit = PLAN_MEMBER_LIMITS.get(plan_slug, PLAN_MEMBER_LIMITS["free_org"])
            set_org_member_limit(org_id, limit)
            # Persist plan in DB so API-key-authenticated endpoints can look it up
            Setting.set(db, org_id, "org_plan", plan_slug)
            # If the subscription is now on a paid plan, clear any lingering
            # past-due flag. Clerk only emits subscription.active/updated once
            # the payment has actually gone through, so seeing this event with
            # a paid plan means the card is good again — the org should get
            # their paid caps back immediately, not after the next
            # paymentAttempt.updated trickles in. Without this clear, an org
            # that upgrades *during* the grace window stays capped at free
            # because effective_plan_for_caps still sees past_due=true.
            if plan_slug in PAID_PLAN_SLUGS_WEBHOOK:
                Setting.set(db, org_id, "payment_past_due", "false")
                Setting.set(db, org_id, "payment_past_due_at", "")
            # Re-evaluate camera cap — a plan change (up or down) may flip
            # rows in either direction. Flushing the Setting first ensures
            # `resolve_org_plan` inside enforce_camera_cap reads the new value.
            db.flush()
            result = enforce_camera_cap(db, org_id)
            if result["changed"]:
                logger.info(
                    "Org %s plan change: disabled=%d enabled=%d",
                    org_id, len(result["disabled"]), len(result["enabled"]),
                )
            logger.info("Org %s subscription active on plan '%s'", org_id, plan_slug)

    # ── Payment failure ─────────────────────────────────────────────
    elif event_type in ("subscription.pastDue", "subscriptionItem.pastDue"):
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            # Record past-due timestamp for grace period tracking.
            # Clerk will retry payment via Stripe dunning. We keep current
            # plan access during the grace period but flag the org.
            Setting.set(db, org_id, "payment_past_due", "true")
            past_due_at = data.get("pastDueAt") or datetime.now(tz=UTC).isoformat()
            Setting.set(db, org_id, "payment_past_due_at", str(past_due_at))
            logger.warning("Org %s subscription is past due — payment failed", org_id)

    # ── Payment attempt result ──────────────────────────────────────
    elif event_type == "paymentAttempt.updated":
        org_id = data.get("payer", {}).get("organization_id")
        payment_status = data.get("status")
        if org_id and payment_status == "paid":
            # Payment succeeded — clear past-due flag and also the
            # timestamp so a future past-due event starts a fresh grace
            # window rather than counting from whenever the old one began.
            Setting.set(db, org_id, "payment_past_due", "false")
            Setting.set(db, org_id, "payment_past_due_at", "")
            # Re-run enforcement so any cameras that got suspended when
            # the grace window expired come back online immediately.
            # effective_plan_for_caps now returns the nominal plan again.
            db.flush()
            result = enforce_camera_cap(db, org_id)
            if result["changed"]:
                logger.info(
                    "Org %s payment restored: re-enabled %d camera(s)",
                    org_id, len(result["enabled"]),
                )
            logger.info("Org %s payment succeeded — past-due cleared", org_id)
        elif org_id and payment_status == "failed":
            logger.warning("Org %s payment attempt failed", org_id)

    # ── Cancellation / end ──────────────────────────────────────────
    elif event_type in ("subscriptionItem.canceled", "subscriptionItem.ended"):
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            # Clerk auto-assigns the free default plan on cancellation,
            # so the JWT pla claim will revert. Just reset member limit.
            set_org_member_limit(org_id, PLAN_MEMBER_LIMITS["free_org"])
            Setting.set(db, org_id, "org_plan", "free_org")
            Setting.set(db, org_id, "payment_past_due", "false")
            # Suspend over-cap cameras now that the org is back on free tier.
            # Rows are preserved (not deleted) so a re-subscribe immediately
            # re-enables them without any reconfiguration.
            db.flush()
            result = enforce_camera_cap(db, org_id)
            if result["changed"]:
                logger.info(
                    "Org %s cancellation: disabled %d over-cap camera(s)",
                    org_id, len(result["disabled"]),
                )
            logger.info("Org %s subscription canceled — reverted to free limits", org_id)

    # ── Free trial ending soon ──────────────────────────────────────
    elif event_type == "subscriptionItem.freeTrialEnding":
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            logger.info("Org %s free trial ending in 3 days", org_id)

    # ── Membership lifecycle (security audit) ──────────────────────
    # Three sibling events fire for the same org's user list churn.
    # Each emits an admin notification so a "did someone just add
    # themselves to my org?" question is answered within seconds
    # rather than the next time someone reads the audit log.  The
    # actor (who DID this — Clerk dashboard admin, the user
    # themselves accepting an invite, etc.) isn't always present in
    # the payload, so the body describes the result rather than the
    # cause; admins can correlate via timing if needed.
    elif event_type == "organizationMembership.created":
        org_data = data.get("organization") or {}
        user_data = data.get("public_user_data") or {}
        org_id = org_data.get("id")
        if org_id:
            try:
                from app.api.notifications import create_notification
                identifier = user_data.get("identifier") or user_data.get("user_id") or "unknown user"
                role = (data.get("role") or "").replace("org:", "") or "member"
                create_notification(
                    org_id=org_id,
                    kind="member_added",
                    title=f"Member added: {identifier}",
                    body=(
                        f"{identifier} was just added to your organization "
                        f"with the {role} role.  If this was via an invite "
                        f"you sent, no action needed.  If you don't recognize "
                        f"this user, audit the org's member list and remove "
                        f"any unexpected accounts."
                    ),
                    severity="warning" if role == "admin" else "info",
                    audience="admin",
                    link="/settings",
                    meta={
                        "user_id": user_data.get("user_id"),
                        "identifier": identifier,
                        "role": role,
                    },
                    db=db,
                )
            except Exception:
                logger.exception(
                    "[ClerkWebhook] member_added notification failed for org=%s",
                    org_id,
                )

    elif event_type == "organizationMembership.updated":
        org_data = data.get("organization") or {}
        user_data = data.get("public_user_data") or {}
        org_id = org_data.get("id")
        if org_id:
            try:
                from app.api.notifications import create_notification
                identifier = user_data.get("identifier") or user_data.get("user_id") or "unknown user"
                role = (data.get("role") or "").replace("org:", "") or "member"
                create_notification(
                    org_id=org_id,
                    kind="member_role_changed",
                    title=f"Member role changed: {identifier}",
                    body=(
                        f"{identifier}'s role in your organization is now "
                        f"{role}.  Role changes — especially promotions to "
                        f"admin — are security-relevant.  If you didn't "
                        f"authorize this change, audit your org's member "
                        f"list immediately."
                    ),
                    # Role escalations to admin are always warning-worthy;
                    # demotions / member-tier changes are informational.
                    severity="warning" if role == "admin" else "info",
                    audience="admin",
                    link="/settings",
                    meta={
                        "user_id": user_data.get("user_id"),
                        "identifier": identifier,
                        "new_role": role,
                    },
                    db=db,
                )
            except Exception:
                logger.exception(
                    "[ClerkWebhook] member_role_changed notification failed for org=%s",
                    org_id,
                )

    elif event_type == "organizationMembership.deleted":
        org_data = data.get("organization") or {}
        user_data = data.get("public_user_data") or {}
        org_id = org_data.get("id")
        if org_id:
            try:
                from app.api.notifications import create_notification
                identifier = user_data.get("identifier") or user_data.get("user_id") or "unknown user"
                create_notification(
                    org_id=org_id,
                    kind="member_removed",
                    title=f"Member removed: {identifier}",
                    body=(
                        f"{identifier} was just removed from your "
                        f"organization.  No further access from this user.  "
                        f"If you didn't expect this removal, audit the org's "
                        f"recent admin activity."
                    ),
                    severity="info",
                    audience="admin",
                    link="/settings",
                    meta={
                        "user_id": user_data.get("user_id"),
                        "identifier": identifier,
                    },
                    db=db,
                )
            except Exception:
                logger.exception(
                    "[ClerkWebhook] member_removed notification failed for org=%s",
                    org_id,
                )

    # ── Organization deleted ───────────────────────────────────────
    elif event_type == "organization.deleted":
        org_id = data.get("id")
        if org_id:
            # Clean up in-memory caches and delete all DB records.
            from app.api.hls import cleanup_camera_cache
            nodes = db.query(CameraNode).filter_by(org_id=org_id).all()
            camera_count = 0
            for node in nodes:
                for camera in (node.cameras or []):
                    cleanup_camera_cache(camera.camera_id)
                    camera_count += 1
                db.delete(node)  # cascade deletes cameras

            group_count = db.query(CameraGroup).filter_by(org_id=org_id).delete()
            key_count = db.query(McpApiKey).filter_by(org_id=org_id).delete()
            db.query(McpActivityLog).filter_by(org_id=org_id).delete()
            db.query(StreamAccessLog).filter_by(org_id=org_id).delete()
            db.query(AuditLog).filter_by(org_id=org_id).delete()
            db.query(Setting).filter_by(org_id=org_id).delete()
            db.commit()

            logger.info(
                "Org %s deleted — cleaned up %d nodes, %d cameras, %d groups, %d API keys",
                org_id, len(nodes), camera_count, group_count, key_count,
            )

    # Mark this msg id as processed so Svix retries short-circuit.
    # Done at the end so a handler that raises midway doesn't record
    # itself as done — Svix retries, idempotent ops re-run, eventual
    # consistency.
    if svix_msg_id:
        try:
            db.add(ProcessedWebhook(
                svix_msg_id=svix_msg_id, event_type=event_type or "",
            ))
            db.commit()
        except Exception:
            # Race: another worker recorded the same id between our
            # check and our insert.  Unique-constraint failure is
            # benign — both runs produce the same final state and the
            # response below still tells Svix we're done.
            db.rollback()
            logger.info(
                "Webhook %s dedup insert raced with concurrent worker — ignoring",
                svix_msg_id,
            )

    return {"received": True}


# ── Resend webhook ─────────────────────────────────────────────────
# Resend signs webhooks via Svix, same library Clerk uses, so we
# verify and dedupe with the identical pattern as ``/api/webhooks/clerk``.
#
# Events we handle:
#   - email.bounced     → insert EmailSuppression so we stop sending
#   - email.complained  → insert EmailSuppression (marked spam by user)
#   - email.delivered   → optional outbox-row update (informational)
#
# Other event types (opened, clicked, scheduled, etc.) are accepted
# (200 OK) but not acted on for v1.  The 200 keeps Resend from
# disabling our endpoint for "unhandled events."

# Reasons we'll record on EmailSuppression rows.  ``email.bounced``
# is anything Resend's SMTP-level retries gave up on (hard bounces);
# ``email.complained`` is the user clicking "spam" in their client.
# Both are signals to stop sending — re-sending after either dings
# our deliverability reputation across ALL recipients.
_RESEND_SUPPRESSION_EVENTS = {
    "email.bounced": "bounce",
    "email.complained": "complaint",
}


@router.post("/resend")
@limiter.limit("600/minute")
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Resend delivery events (bounce, complaint, etc.).

    Mirrors the Clerk webhook pattern exactly: HMAC verification via
    Svix, idempotency via ``ProcessedWebhook``, dispatch by event type.
    Reuses the existing ``ProcessedWebhook`` table because Svix message
    IDs are UUIDs — collision between Clerk and Resend is statistically
    impossible, and even if one occurred the unique constraint would
    fail safely.

    The 600/min rate limit is generous because Resend bursts events
    when a delivery campaign completes.  Real volume is far below this.
    """
    payload = await request.body()
    headers = dict(request.headers)

    if not settings.RESEND_WEBHOOK_SECRET:
        # Without the secret we can't verify signatures, so refusing
        # is the only safe thing.  An attacker who knows the URL but
        # not the secret would otherwise be able to forge bounce
        # events to suppress legitimate users.
        logger.error(
            "RESEND_WEBHOOK_SECRET not set — cannot verify Resend signatures"
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook processing unavailable")

    try:
        wh = Webhook(settings.RESEND_WEBHOOK_SECRET)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from None

    # Resend's event payload shape:
    #   {"type": "email.bounced", "data": {"email_id": "...", "to": ["..."], ...}, "created_at": "..."}
    event_type = event.get("type") or ""
    data = event.get("data") or {}

    # ── Idempotency check (mirrors Clerk handler) ──────────────────
    svix_msg_id = headers.get("svix-id")
    if svix_msg_id:
        already = (
            db.query(ProcessedWebhook)
            .filter_by(svix_msg_id=svix_msg_id)
            .first()
        )
        if already:
            logger.info(
                "Resend webhook %s already processed (event=%s) — skipping",
                svix_msg_id, already.event_type or "?",
            )
            return {"status": "duplicate", "svix_id": svix_msg_id}

    logger.info("Resend webhook received: %s", event_type)

    # ── Dispatch ────────────────────────────────────────────────────
    if event_type in _RESEND_SUPPRESSION_EVENTS:
        reason = _RESEND_SUPPRESSION_EVENTS[event_type]
        addresses = _extract_addresses(data)
        for addr in addresses:
            _insert_suppression(db, addr, reason=reason, source="resend_webhook")

        # Mark the originating outbox row 'suppressed' if we can find
        # it via the email_id Resend sends.  Updating after-the-fact
        # is informational — the suppression-list check on the next
        # send is what actually stops further attempts.
        email_id = data.get("email_id")
        if email_id:
            try:
                row = (
                    db.query(EmailOutbox)
                    .filter(EmailOutbox.resend_message_id == email_id)
                    .first()
                )
                if row and row.status == "sent":
                    row.status = "suppressed"
                    row.error = f"webhook_event:{event_type}:reason={reason}"
                    db.commit()
            except Exception:
                logger.exception(
                    "[ResendWebhook] failed to mark outbox row suppressed for email_id=%s",
                    email_id,
                )
                db.rollback()

    elif event_type == "email.delivered":
        # Informational — we already marked the row 'sent' when the
        # API call returned.  Nothing to do, but logged so an operator
        # can correlate "sent at T+0" with "delivered at T+5s" if a
        # support ticket comes in about latency.
        email_id = data.get("email_id")
        if email_id:
            logger.info(
                "[ResendWebhook] delivered confirmation for email_id=%s",
                email_id,
            )

    # Mark this message id as processed so Resend retries short-circuit.
    if svix_msg_id:
        try:
            db.add(ProcessedWebhook(
                svix_msg_id=svix_msg_id, event_type=event_type or "",
            ))
            db.commit()
        except Exception:
            db.rollback()
            logger.info(
                "Resend webhook %s dedup insert raced — ignoring",
                svix_msg_id,
            )

    return {"received": True}


def _extract_addresses(data: dict) -> list[str]:
    """Pull recipient addresses out of a Resend event payload.

    Resend sometimes sends ``to`` as a list, sometimes as a string,
    depending on the event type and SDK version.  Handle both, plus
    the edge case where it's missing entirely (we get nothing useful
    so we don't suppress anyone — better than suppressing the wrong
    address)."""
    to = data.get("to")
    if isinstance(to, list):
        return [a for a in to if isinstance(a, str) and "@" in a]
    if isinstance(to, str) and "@" in to:
        return [to]
    return []


def _insert_suppression(
    db: Session, address: str, *, reason: str, source: str
) -> None:
    """Insert into EmailSuppression, swallowing duplicate-key errors.

    Address is lower-cased to match the worker's case-insensitive
    suppression check (test_email_worker.py covers this).  Race
    between two Resend retries delivering the same bounce gets
    handled by the unique constraint — we treat the rollback as
    benign (the address is already suppressed; mission accomplished).
    """
    addr = (address or "").strip().lower()
    if not addr or "@" not in addr:
        return
    try:
        db.add(EmailSuppression(address=addr, reason=reason, source=source))
        db.commit()
        logger.info(
            "[ResendWebhook] suppressed address=%s reason=%s source=%s",
            _redact_addr(addr), reason, source,
        )
    except Exception:
        db.rollback()
        # Either an existing row (benign) or a real error.  Log at
        # debug to keep the steady-state webhook noise down.
        logger.debug(
            "[ResendWebhook] suppression insert failed (likely duplicate) "
            "for address=%s reason=%s",
            _redact_addr(addr), reason,
        )


def _redact_addr(addr: str) -> str:
    """Same redaction shape as app/core/email.py — keep PII out of logs."""
    if not addr or "@" not in addr:
        return "***"
    local, _, domain = addr.partition("@")
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"
