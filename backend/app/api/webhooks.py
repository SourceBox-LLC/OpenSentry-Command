import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError
from app.core.config import settings
from app.core.clerk import clerk
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.plans import enforce_camera_cap
from app.models.models import Setting, CameraNode, Camera, McpApiKey, McpActivityLog, StreamAccessLog, AuditLog, CameraGroup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Member limits per plan — must match Clerk Dashboard plan keys.
PLAN_MEMBER_LIMITS = {
    "free_org": 2,
    "pro": 10,
    "business": 20,
}

# Paid plan slugs. Seeing a subscription.updated with one of these means the
# payment card is active (Clerk wouldn't mark the subscription live otherwise),
# so we can clear any past-due flag we were holding. Kept local to this module
# rather than imported from plans.py to keep webhook semantics self-contained.
PAID_PLAN_SLUGS_WEBHOOK = frozenset({"pro", "business"})


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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")

    event_type = event.get("type")
    data = event.get("data", {})

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
            past_due_at = data.get("pastDueAt") or datetime.now(tz=timezone.utc).isoformat()
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

    return {"received": True}
