import logging
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError
from app.core.config import settings
from app.core.clerk import clerk
from app.core.database import get_db
from app.models.models import Setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Member limits per plan — must match Clerk Dashboard plan keys.
PLAN_MEMBER_LIMITS = {
    "free_org": 2,
    "pro": 10,
    "business": 20,
}


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
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    headers = dict(request.headers)

    if not settings.CLERK_WEBHOOK_SECRET:
        logger.warning("CLERK_WEBHOOK_SECRET not set — rejecting unverified webhook")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Webhook secret not configured")

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
            logger.info("Org %s subscription active on plan '%s'", org_id, plan_slug)

    # ── Payment failure ─────────────────────────────────────────────
    elif event_type == "subscription.pastDue":
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            logger.warning("Org %s subscription is past due — payment failed", org_id)
            # Keep current limits for a grace period; Clerk will retry payment.
            # If you want to restrict access, downgrade here.

    # ── Cancellation / end ──────────────────────────────────────────
    elif event_type in ("subscriptionItem.canceled", "subscriptionItem.ended"):
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            # Clerk auto-assigns the free default plan on cancellation,
            # so the JWT pla claim will revert. Just reset member limit.
            set_org_member_limit(org_id, PLAN_MEMBER_LIMITS["free_org"])
            Setting.set(db, org_id, "org_plan", "free_org")
            logger.info("Org %s subscription canceled — reverted to free limits", org_id)

    # ── Free trial ending soon ──────────────────────────────────────
    elif event_type == "subscriptionItem.freeTrialEnding":
        org_id = data.get("payer", {}).get("organization_id")
        if org_id:
            logger.info("Org %s free trial ending in 3 days", org_id)
            # Future: send notification email

    return {"received": True}
