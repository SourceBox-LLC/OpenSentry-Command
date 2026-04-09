"""
Plan configuration and limit enforcement for OpenSentry billing tiers.

Plan slugs must match the keys defined in the Clerk Dashboard:
  - free_org  (Free)
  - pro       (Pro — $19/mo)
  - business  (Business — $49/mo)
"""

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


def get_plan_limits(plan: str) -> dict:
    """Return the limits dict for a plan slug. Falls back to free tier."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free_org"])


def get_plan_limits_for_org(db, org_id: str) -> dict:
    """Look up an org's plan from the database and return its limits.

    Used by endpoints that authenticate via API key (e.g. node registration)
    where JWT claims are not available.  The plan is stored as a Setting
    by the Clerk webhook handler whenever a subscription changes.
    """
    from app.models.models import Setting

    plan = Setting.get(db, org_id, "org_plan", "free_org")
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
