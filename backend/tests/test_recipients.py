"""
Tests for the email recipient lookup (app/core/recipients.py).

The Clerk SDK is monkeypatched at the ``recipients.clerk`` binding —
every test runs against a stub that returns a controlled membership
list, so the actual SDK never makes a network call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import recipients


# ── Test fixtures ───────────────────────────────────────────────────

def _membership(role: str, identifier: str | None) -> SimpleNamespace:
    """Mimic the shape of clerk_backend_api.OrganizationMembership.

    Only the fields recipients._extract_email touches — keeps tests
    insulated from SDK schema changes that don't affect us."""
    return SimpleNamespace(
        role=role,
        public_user_data=SimpleNamespace(identifier=identifier),
    )


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """The cache is module-global — without this every test would
    leak state into the next.  Mirrors conftest's other autouse
    cleanup fixtures."""
    recipients._clear_cache()
    yield
    recipients._clear_cache()


@pytest.fixture
def fake_clerk(monkeypatch):
    """Yields a controllable stub for ``clerk.organization_memberships.list``.

    Tests assign ``stub.members`` (list of memberships) and read
    ``stub.calls`` (count of API calls — used to verify caching)."""
    class Stub:
        def __init__(self):
            self.members: list = []
            self.calls = 0
            self.raise_on_call: Exception | None = None

        def list(self, *, organization_id, limit=10, **kwargs):
            self.calls += 1
            if self.raise_on_call:
                raise self.raise_on_call
            return SimpleNamespace(data=list(self.members), total_count=len(self.members))

    stub = Stub()
    monkeypatch.setattr(recipients.clerk, "organization_memberships", stub)
    return stub


# ── Audience filter ─────────────────────────────────────────────────

def test_audience_all_returns_every_member(fake_clerk):
    """Audience='all' returns admins + members alike."""
    fake_clerk.members = [
        _membership("org:admin", "admin@example.com"),
        _membership("org:member", "member1@example.com"),
        _membership("org:member", "member2@example.com"),
    ]

    addrs = recipients.get_recipient_emails("org_x", "all")

    assert sorted(addrs) == [
        "admin@example.com", "member1@example.com", "member2@example.com",
    ]


def test_audience_admin_filters_to_admins_only(fake_clerk):
    """Audience='admin' drops non-admin members.  Used for
    admin-only customer events (e.g. node_offline)."""
    fake_clerk.members = [
        _membership("org:admin", "admin@example.com"),
        _membership("org:member", "member@example.com"),
    ]

    addrs = recipients.get_recipient_emails("org_x", "admin")

    assert addrs == ["admin@example.com"]


def test_audience_unknown_falls_through_to_all(fake_clerk):
    """An unrecognised audience string (typo, future audience) must
    NOT silently drop emails — fall through to 'all' so the alert
    still goes out."""
    fake_clerk.members = [
        _membership("org:admin", "admin@example.com"),
        _membership("org:member", "member@example.com"),
    ]

    addrs = recipients.get_recipient_emails("org_x", "operator_only_typo")

    assert sorted(addrs) == ["admin@example.com", "member@example.com"]


# ── Identifier handling ─────────────────────────────────────────────

def test_non_email_identifier_is_skipped(fake_clerk):
    """Username-auth users have a non-email ``identifier``.  We can't
    email them anyway, so skip silently."""
    fake_clerk.members = [
        _membership("org:admin", "admin@example.com"),
        _membership("org:member", "username_only"),  # no @
        _membership("org:member", None),             # missing entirely
    ]

    addrs = recipients.get_recipient_emails("org_x", "all")

    assert addrs == ["admin@example.com"]


def test_duplicate_addresses_are_deduplicated(fake_clerk):
    """Two memberships pointing to the same address (case-insensitive)
    return one entry — protects against double-emails to a user who
    somehow ends up in the org membership list twice."""
    fake_clerk.members = [
        _membership("org:admin", "Alice@Example.com"),
        _membership("org:member", "alice@example.com"),
    ]

    addrs = recipients.get_recipient_emails("org_x", "all")

    assert len(addrs) == 1


# ── Caching ─────────────────────────────────────────────────────────

def test_repeat_calls_within_ttl_use_cache(fake_clerk):
    """Two calls with the same key → only one Clerk API call.
    Critical for flap events (camera offline / online / offline /
    online over 30 seconds) — without caching that's 4 Clerk calls
    per flap per active org."""
    fake_clerk.members = [_membership("org:admin", "a@x.test")]

    recipients.get_recipient_emails("org_x", "all")
    recipients.get_recipient_emails("org_x", "all")
    recipients.get_recipient_emails("org_x", "all")

    assert fake_clerk.calls == 1


def test_different_audiences_cache_separately(fake_clerk):
    """Cache key is (org_id, audience) — same org with different
    audiences is two cache entries, not one."""
    fake_clerk.members = [
        _membership("org:admin", "admin@x.test"),
        _membership("org:member", "member@x.test"),
    ]

    recipients.get_recipient_emails("org_x", "all")
    recipients.get_recipient_emails("org_x", "admin")
    recipients.get_recipient_emails("org_x", "all")  # cached
    recipients.get_recipient_emails("org_x", "admin")  # cached

    assert fake_clerk.calls == 2


def test_invalidate_org_drops_cache(fake_clerk):
    """invalidate_org() clears all entries for an org so the next
    lookup re-hits Clerk.  Hook for the future
    organizationMembership.created/deleted webhook handler."""
    fake_clerk.members = [_membership("org:admin", "a@x.test")]

    recipients.get_recipient_emails("org_x", "all")
    recipients.get_recipient_emails("org_x", "admin")
    assert fake_clerk.calls == 2

    recipients.invalidate_org("org_x")

    recipients.get_recipient_emails("org_x", "all")
    recipients.get_recipient_emails("org_x", "admin")
    assert fake_clerk.calls == 4


def test_cache_is_per_org(fake_clerk):
    """Different orgs cache independently — no cross-tenant cache
    pollution."""
    fake_clerk.members = [_membership("org:admin", "a@x.test")]

    recipients.get_recipient_emails("org_a", "all")
    recipients.get_recipient_emails("org_b", "all")
    recipients.get_recipient_emails("org_a", "all")  # cached
    recipients.get_recipient_emails("org_b", "all")  # cached

    assert fake_clerk.calls == 2


# ── Failure handling ────────────────────────────────────────────────

def test_clerk_failure_returns_empty_list(fake_clerk):
    """Clerk outage → return []. The worker treats no recipients as
    'no-op tick', which is the safe default — beats crashing the
    worker forever during a Clerk incident."""
    fake_clerk.raise_on_call = ConnectionError("Clerk down")

    addrs = recipients.get_recipient_emails("org_x", "all")

    assert addrs == []


def test_clerk_returns_empty_membership(fake_clerk):
    """Org exists but has no members per Clerk — returns []."""
    fake_clerk.members = []

    addrs = recipients.get_recipient_emails("org_x", "all")

    assert addrs == []


def test_returned_list_is_a_copy(fake_clerk):
    """Caller can mutate the returned list without poisoning the
    cache — cheap defensive copy."""
    fake_clerk.members = [_membership("org:admin", "a@x.test")]

    first = recipients.get_recipient_emails("org_x", "all")
    first.append("evil@attacker.test")

    second = recipients.get_recipient_emails("org_x", "all")
    assert second == ["a@x.test"]
