"""Clerk webhook integration tests.

These cover the code-level plumbing of subscription lifecycle events
(created / updated / canceled / past-due) into the `Setting(org_plan)`
cache that the rest of the backend reads for feature gating.

A silent regression here means a paying customer never actually gets
the paid tier — so we sign real svix payloads and POST them at the
endpoint, rather than mocking `Webhook.verify()`. If the signature
verification path breaks, these tests break with it.
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from svix.webhooks import Webhook

from app.core.config import settings
from app.models.models import Setting

TEST_ORG_ID = "org_test123"
# Fixed test secret so every test signs with the same key. Format matches
# Clerk's whsec_<base64> convention; the body is a throwaway 32-byte key.
TEST_WEBHOOK_SECRET = "whsec_dGVzdHNlY3JldHRlc3RzZWNyZXR0ZXN0c2VjcmV0MTI="


def _signed_post(client, event_type: str, data: dict, *, secret: str = TEST_WEBHOOK_SECRET):
    """POST a signed Clerk-style webhook to /api/webhooks/clerk."""
    payload = json.dumps({"type": event_type, "data": data})
    msg_id = f"msg_{event_type.replace('.', '_')}_test"
    ts = datetime.now(tz=timezone.utc)

    sig = Webhook(secret).sign(msg_id, ts, payload)

    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": sig,
        "content-type": "application/json",
    }
    return client.post("/api/webhooks/clerk", content=payload, headers=headers)


@pytest.fixture
def webhook_client(unauthenticated_client, monkeypatch):
    """Client with CLERK_WEBHOOK_SECRET configured + Clerk SDK stubbed.

    `clerk.organizations.update` is called from `set_org_member_limit`.
    Without a real Clerk API it raises, and while the handler catches
    it, the stack trace pollutes test output. Stubbing keeps the logs
    quiet and makes failures easier to read.
    """
    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)
    with patch("app.api.webhooks.clerk.organizations.update"):
        yield unauthenticated_client


# ─── Subscription lifecycle ─────────────────────────────────────────

def test_subscription_created_sets_org_plan_to_pro(webhook_client, db):
    """The most important billing test in the repo: when Clerk fires
    `subscription.created` with an active pro item, the handler persists
    `org_plan=pro`. A regression here silently keeps every paying
    customer on free_org."""
    resp = _signed_post(webhook_client, "subscription.created", {
        "payer": {"organization_id": TEST_ORG_ID},
        "items": [{"status": "active", "plan": {"slug": "pro"}}],
    })
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "pro"


def test_subscription_updated_flips_plan_pro_to_business(webhook_client, db):
    """Upgrade path: the new slug overwrites the cached one."""
    Setting.set(db, TEST_ORG_ID, "org_plan", "pro")

    resp = _signed_post(webhook_client, "subscription.updated", {
        "payer": {"organization_id": TEST_ORG_ID},
        "items": [{"status": "active", "plan": {"slug": "business"}}],
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "business"


def test_subscription_active_also_sets_plan(webhook_client, db):
    """`subscription.active` is treated the same as created/updated —
    some Clerk configurations fire this event instead of the other two."""
    resp = _signed_post(webhook_client, "subscription.active", {
        "payer": {"organization_id": TEST_ORG_ID},
        "items": [{"status": "active", "plan": {"slug": "pro"}}],
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "pro"


def test_subscription_item_canceled_reverts_to_free_org(webhook_client, db):
    """Cancellation reverts the cached plan and clears past-due."""
    Setting.set(db, TEST_ORG_ID, "org_plan", "pro")
    Setting.set(db, TEST_ORG_ID, "payment_past_due", "true")

    resp = _signed_post(webhook_client, "subscriptionItem.canceled", {
        "payer": {"organization_id": TEST_ORG_ID},
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "free_org"
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") == "false"


def test_subscription_item_ended_also_reverts(webhook_client, db):
    """`subscriptionItem.ended` should behave like canceled."""
    Setting.set(db, TEST_ORG_ID, "org_plan", "business")

    resp = _signed_post(webhook_client, "subscriptionItem.ended", {
        "payer": {"organization_id": TEST_ORG_ID},
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "free_org"


# ─── Payment states ────────────────────────────────────────────────

def test_past_due_sets_flag(webhook_client, db):
    """`subscription.pastDue` sets `payment_past_due=true`. The plan
    stays intact during the grace period so the user isn't demoted the
    moment a card declines; `require_active_billing` handles blocking
    writes separately."""
    resp = _signed_post(webhook_client, "subscription.pastDue", {
        "payer": {"organization_id": TEST_ORG_ID},
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") == "true"


def test_subscription_item_past_due_also_sets_flag(webhook_client, db):
    """The item-level `subscriptionItem.pastDue` is handled the same."""
    resp = _signed_post(webhook_client, "subscriptionItem.pastDue", {
        "payer": {"organization_id": TEST_ORG_ID},
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") == "true"


def test_payment_paid_clears_past_due(webhook_client, db):
    """`paymentAttempt.updated` with status=paid clears the flag so the
    org can write again without manual intervention."""
    Setting.set(db, TEST_ORG_ID, "payment_past_due", "true")

    resp = _signed_post(webhook_client, "paymentAttempt.updated", {
        "payer": {"organization_id": TEST_ORG_ID},
        "status": "paid",
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") == "false"


def test_payment_failed_does_not_clear_past_due(webhook_client, db):
    """A failed retry must NOT clear the flag."""
    Setting.set(db, TEST_ORG_ID, "payment_past_due", "true")

    resp = _signed_post(webhook_client, "paymentAttempt.updated", {
        "payer": {"organization_id": TEST_ORG_ID},
        "status": "failed",
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") == "true"


# ─── Security ──────────────────────────────────────────────────────

def test_invalid_signature_rejected(webhook_client, db):
    """A payload signed with the wrong secret is rejected with 400 and
    produces no side effect."""
    resp = _signed_post(
        webhook_client,
        "subscription.created",
        {
            "payer": {"organization_id": TEST_ORG_ID},
            "items": [{"status": "active", "plan": {"slug": "pro"}}],
        },
        secret="whsec_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    assert resp.status_code == 400
    assert Setting.get(db, TEST_ORG_ID, "org_plan") is None


def test_missing_webhook_secret_fails_closed(unauthenticated_client, monkeypatch, db):
    """Without `CLERK_WEBHOOK_SECRET` configured the endpoint MUST fail
    closed — never silently accept unsigned payloads. A silent-accept
    regression would give anyone on the internet write access to the
    billing cache."""
    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", "")

    resp = unauthenticated_client.post(
        "/api/webhooks/clerk",
        json={
            "type": "subscription.created",
            "data": {
                "payer": {"organization_id": TEST_ORG_ID},
                "items": [{"status": "active", "plan": {"slug": "pro"}}],
            },
        },
    )
    assert resp.status_code == 400
    assert Setting.get(db, TEST_ORG_ID, "org_plan") is None


# ─── Edge cases ────────────────────────────────────────────────────

def test_unknown_plan_slug_stored_verbatim(webhook_client, db):
    """Clerk dashboards configured with non-matching slugs ('Pro' with
    a capital P, 'pro-v2', etc.) are the #1 production misconfig for
    this path. We store whatever slug Clerk sent so an operator can
    see it in the DB and spot the mismatch — better than silently
    dropping to free_org and leaving no trace."""
    resp = _signed_post(webhook_client, "subscription.created", {
        "payer": {"organization_id": TEST_ORG_ID},
        "items": [{"status": "active", "plan": {"slug": "unknown_slug"}}],
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "unknown_slug"


def test_subscription_with_no_active_items_resolves_to_free(webhook_client, db):
    """All-paused subscriptions resolve to free_org via
    `get_active_plan_slug`'s fallback."""
    resp = _signed_post(webhook_client, "subscription.updated", {
        "payer": {"organization_id": TEST_ORG_ID},
        "items": [{"status": "paused", "plan": {"slug": "pro"}}],
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") == "free_org"


def test_webhook_without_org_id_is_noop(webhook_client, db):
    """Malformed payloads missing `payer.organization_id` are ignored
    gracefully (200) rather than crashing the endpoint — Clerk retries
    on 5xx, so a crash would compound the problem."""
    resp = _signed_post(webhook_client, "subscription.created", {
        "items": [{"status": "active", "plan": {"slug": "pro"}}],
    })
    assert resp.status_code == 200
    # Nothing written
    assert Setting.get(db, TEST_ORG_ID, "org_plan") is None


def test_org_deleted_purges_settings(webhook_client, db):
    """`organization.deleted` wipes all org-scoped data. We verify the
    Setting deletion here; the broader cascade (nodes/cameras/keys) is
    covered by the integration test in test_security.py when org data
    is scoped. If THIS fails, we leak org data after account deletion."""
    Setting.set(db, TEST_ORG_ID, "org_plan", "pro")
    Setting.set(db, TEST_ORG_ID, "payment_past_due", "false")

    resp = _signed_post(webhook_client, "organization.deleted", {
        "id": TEST_ORG_ID,
    })
    assert resp.status_code == 200
    assert Setting.get(db, TEST_ORG_ID, "org_plan") is None
    assert Setting.get(db, TEST_ORG_ID, "payment_past_due") is None
