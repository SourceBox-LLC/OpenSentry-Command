"""
Plan configuration and limit enforcement for SourceBox Sentry billing tiers.

Plan slugs must match the keys defined in the Clerk Dashboard:
  - free_org  (Free)
  - pro       (Pro — $19/mo)
  - business  (Business — $49/mo)
"""

import logging
import time

logger = logging.getLogger(__name__)

PLAN_LIMITS = {
    "free_org": {
        "max_cameras": 2,
        "max_nodes": 1,
    },
    "pro": {
        "max_cameras": 10,
        "max_nodes": 5,
    },
    "business": {
        "max_cameras": 50,
        "max_nodes": 999,  # effectively unlimited
    },
}

# Slugs we trust without re-checking against Clerk.
PAID_PLAN_SLUGS = frozenset({"pro", "business"})

# Min seconds between consecutive live Clerk lookups for the same org.
# Prevents non-paid callers from generating excessive Clerk API traffic
# when they hit the MCP gate repeatedly.
_RESOLVE_THROTTLE_SECONDS = 60.0
_last_resolve_at: dict[str, float] = {}


def get_plan_limits(plan: str) -> dict:
    """Return the limits dict for a plan slug. Falls back to free tier."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free_org"])


def resolve_org_plan(db, org_id: str) -> str:
    """Return the current plan slug for an org, with a Clerk fallback.

    Read order:
      1. Cached `Setting(org_plan)` — populated by the Clerk webhook
         handler in app/api/webhooks.py. If the value is a recognized
         paid plan, return immediately (fast path, no API call).
      2. Live `clerk.organizations.get_billing_subscription()` — fixes
         orgs whose subscription webhook never fired (e.g. they
         upgraded before the handler shipped, delivery failed, or the
         dashboard plan name produced a slug that didn't match a key
         in PLAN_LIMITS). The fresh slug is written back to the
         Setting so future calls hit the fast path.

    Live lookups for the same org are throttled to once per 60 seconds
    so a free-tier caller hammering MCP can't drive Clerk API spend.
    """
    from app.models.models import Setting
    from app.core.clerk import clerk

    cached = Setting.get(db, org_id, "org_plan", "")
    if cached in PAID_PLAN_SLUGS:
        return cached

    # Throttle live re-checks per org.
    now = time.monotonic()
    if now - _last_resolve_at.get(org_id, 0.0) < _RESOLVE_THROTTLE_SECONDS:
        return cached or "free_org"
    _last_resolve_at[org_id] = now

    try:
        sub = clerk.organizations.get_billing_subscription(organization_id=org_id)
    except Exception:
        logger.warning(
            "Live Clerk plan lookup failed for org %s — returning cached value %r",
            org_id, cached, exc_info=True,
        )
        return cached or "free_org"

    # Mirror the webhook handler's logic: take the first active item's plan slug.
    live_slug = "free_org"
    for item in (sub.subscription_items or []):
        status = getattr(item, "status", None)
        plan = getattr(item, "plan", None)
        if status == "active" and plan and getattr(plan, "slug", None):
            live_slug = plan.slug
            break

    if live_slug != cached:
        Setting.set(db, org_id, "org_plan", live_slug)
        try:
            db.commit()
            logger.info(
                "Resolved org %s plan from Clerk: cached=%r → live=%r",
                org_id, cached, live_slug,
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to persist resolved plan for org %s", org_id)

    return live_slug


def get_plan_limits_for_org(db, org_id: str) -> dict:
    """Look up an org's plan from the database and return its limits.

    Used by endpoints that authenticate via API key (e.g. node registration)
    where JWT claims are not available.  Falls back to a live Clerk lookup
    if the cached Setting is stale or missing — see ``resolve_org_plan``.
    """
    plan = resolve_org_plan(db, org_id)
    limits = get_plan_limits(plan)
    # Attach the plan slug so callers can show a display name
    return {**limits, "_plan": plan}


def get_plan_display_name(plan: str) -> str:
    """Human-readable plan name."""
    names = {
        "free_org": "Free",
        "pro": "Pro",
        "business": "Business",
    }
    return names.get(plan, "Free")


def enforce_camera_cap(db, org_id: str) -> dict:
    """Enforce the org's current camera cap by flipping ``Camera.disabled_by_plan``.

    Keeps the oldest ``max_cameras`` cameras (by ``created_at`` ascending — the
    ones the org has had the longest) enabled, flags the rest as
    ``disabled_by_plan=True``. On upgrade (cap raised above current count) all
    flags are cleared. Idempotent: safe to call on every registration and
    subscription webhook with no state change when nothing needs to flip.

    Why oldest-first:
      - Deterministic, no user input required.
      - Preserves long-running cameras that almost certainly have history /
        recordings the operator cares about.
      - Newer cameras the operator just plugged in are easier to replace
        (you remember setting them up this week) than a year-old camera.

    The flag is consulted by ``POST /push-segment`` which rejects uploads
    with HTTP 402 + ``plan_limit_hit`` body when set. Enforcement is *only*
    at upload time — we don't delete rows, so on upgrade the disabled
    cameras light back up immediately with all their metadata intact.

    Returns a dict:
      {
          "plan": "free",                 # wire slug
          "max_cameras": 2,
          "disabled": ["cam_03", ...],    # camera_ids newly or still disabled
          "enabled": ["cam_01", ...],     # camera_ids newly or still enabled
          "changed": True,                # whether any row flipped
      }

    The caller commits.
    """
    from app.models.models import Camera  # local import — plans.py is
    # depended on by many modules, keep the import graph flat.

    plan_slug = resolve_org_plan(db, org_id)
    limits = get_plan_limits(plan_slug)
    cap = int(limits["max_cameras"])

    # Ordered by created_at ASC; None last (shouldn't happen in practice
    # since `created_at` has a default, but be defensive).
    cameras = (
        db.query(Camera)
        .filter_by(org_id=org_id)
        .order_by(Camera.created_at.asc().nulls_last(), Camera.id.asc())
        .all()
    )

    keep_ids = {c.camera_id for c in cameras[:cap]}
    disable_ids = [c.camera_id for c in cameras[cap:]]

    changed = False
    enabled: list[str] = []
    disabled: list[str] = []
    for cam in cameras:
        should_disable = cam.camera_id not in keep_ids
        if bool(cam.disabled_by_plan) != should_disable:
            cam.disabled_by_plan = should_disable
            changed = True
        (disabled if should_disable else enabled).append(cam.camera_id)

    if changed:
        logger.info(
            "enforce_camera_cap: org=%s plan=%s cap=%d enabled=%d disabled=%d",
            org_id, plan_slug, cap, len(enabled), len(disabled),
        )

    return {
        "plan": wire_plan_slug(plan_slug),
        "max_cameras": cap,
        "enabled": enabled,
        "disabled": disable_ids,
        "changed": changed,
    }


def wire_plan_slug(plan: str) -> str:
    """Canonical plan string for the CloudNode wire protocol.

    Strips the internal ``_org`` suffix so the node renders a clean pill
    badge (``[ FREE ]`` rather than ``[ FREE_ORG ]``). Unknown slugs pass
    through untouched so a future tier like ``enterprise`` shows up in
    the node UI before we ship a node update.

    The CloudNode treats this field as advisory — enforcement still lives
    here in the backend — so a stale / unexpected value doesn't affect
    access, only the label in the status bar.
    """
    plan = (plan or "").strip().lower()
    if not plan:
        return "free"
    if plan.endswith("_org"):
        return plan[: -len("_org")]
    return plan
