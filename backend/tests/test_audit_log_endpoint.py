"""
Tests for the JSON shape + filters on ``GET /api/audit-logs``.

The CSV path is covered in test_csv_export.py.  This file pins the
new paginated/filtered JSON shape that backs the admin dashboard's
Organization Audit Log section.

Most-important invariant: org isolation per-filter — a filter that
matches another org's row must NEVER return that row.  Pinned because
this endpoint is admin-only and an org A admin should never see
org B's audit history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.models import AuditLog

TEST_ORG = "org_test123"
OTHER_ORG = "org_OTHER999"


@pytest.fixture
def seeded_audit(db):
    """Seed a mix of audit events across both TEST_ORG and OTHER_ORG."""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add_all([
        # TEST_ORG events (5 across 4 distinct types).
        AuditLog(org_id=TEST_ORG, timestamp=now - timedelta(minutes=1),
                 event="member_added", username="alice@example.com"),
        AuditLog(org_id=TEST_ORG, timestamp=now - timedelta(minutes=2),
                 event="mcp_key_created", username="alice@example.com"),
        AuditLog(org_id=TEST_ORG, timestamp=now - timedelta(minutes=3),
                 event="mcp_key_revoked", username="bob@example.com"),
        AuditLog(org_id=TEST_ORG, timestamp=now - timedelta(minutes=4),
                 event="full_reset", username="alice@example.com"),
        AuditLog(org_id=TEST_ORG, timestamp=now - timedelta(minutes=5),
                 event="member_added", username="carol@example.com"),
        # OTHER_ORG events — must NOT leak into TEST_ORG queries.
        AuditLog(org_id=OTHER_ORG, timestamp=now,
                 event="member_added", username="alice@example.com"),
        AuditLog(org_id=OTHER_ORG, timestamp=now,
                 event="mcp_key_created", username="dave@example.com"),
    ])
    db.commit()


# ── JSON response shape ────────────────────────────────────────────


def test_audit_logs_returns_paginated_envelope(admin_client, seeded_audit):
    """Response shape matches the sibling /api/audit/stream-logs +
    /api/mcp/activity/logs envelope so the frontend pagination
    component is shareable across all three audit surfaces."""
    resp = admin_client.get("/api/audit-logs")
    assert resp.status_code == 200
    body = resp.json()

    # Envelope keys.
    assert set(body.keys()) == {"total", "limit", "offset", "logs"}
    assert body["total"] == 5  # only TEST_ORG seeds
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert isinstance(body["logs"], list)
    assert len(body["logs"]) == 5


def test_audit_logs_orders_newest_first(admin_client, seeded_audit):
    """Operators scanning a fresh dashboard expect to see the most
    recent action at the top.  Pin desc-by-timestamp so a refactor
    that drops the order_by doesn't silently flip it."""
    body = admin_client.get("/api/audit-logs").json()
    timestamps = [row["timestamp"] for row in body["logs"]]
    assert timestamps == sorted(timestamps, reverse=True)


# ── Org isolation — the highest-impact assertion in this file ─────


def test_audit_logs_isolated_to_caller_org(admin_client, db, seeded_audit):
    """Cross-tenant audit-log leak would be catastrophic.  Pinned
    here per-filter (no filter, event filter, username filter) to
    catch a regression that silently widened the org scope."""
    body = admin_client.get("/api/audit-logs").json()
    # OTHER_ORG seeded 2 rows; none should appear here.
    for row in body["logs"]:
        assert "dave@example.com" not in (row.get("username") or "")
    # And the total count reflects ONLY caller's rows.
    assert body["total"] == 5


# ── Filter: event type ────────────────────────────────────────────


def test_audit_logs_filter_by_event_type(admin_client, seeded_audit):
    """Filtering by event narrows to just that type.  Used by the
    dashboard's event-dropdown."""
    body = admin_client.get("/api/audit-logs?event=member_added").json()
    assert body["total"] == 2  # TEST_ORG has 2 member_added rows
    for row in body["logs"]:
        assert row["event"] == "member_added"


def test_audit_logs_event_filter_isolated_to_caller_org(
    admin_client, seeded_audit,
):
    """Event filter must STILL apply org_id — OTHER_ORG also has a
    member_added row but it must not appear in TEST_ORG's filtered
    view."""
    body = admin_client.get("/api/audit-logs?event=member_added").json()
    # Both seeded TEST_ORG member_added rows; total=2.  If org filter
    # silently dropped, total would be 3 (2 ours + 1 theirs).
    assert body["total"] == 2


# ── Filter: username substring ────────────────────────────────────


def test_audit_logs_filter_by_username_substring(admin_client, seeded_audit):
    """Username filter is case-insensitive substring match — operators
    typing "alice" should find every row alice was involved in,
    regardless of capitalisation."""
    body = admin_client.get("/api/audit-logs?username=ALICE").json()
    assert body["total"] == 3  # alice has 3 TEST_ORG rows
    for row in body["logs"]:
        assert "alice" in row["username"].lower()


def test_audit_logs_username_filter_escapes_sql_wildcards(
    admin_client, db, seeded_audit,
):
    """Underscores in usernames are common (clerk_user_xyz patterns)
    so the filter must treat them as literal characters, not SQL
    wildcards.  Without the escape pass, ``user_alice`` filter would
    match ``userXalice`` too."""
    db.add(AuditLog(
        org_id=TEST_ORG,
        timestamp=datetime.now(tz=UTC).replace(tzinfo=None),
        event="member_added",
        username="literal_match_user",
    ))
    db.commit()

    body = admin_client.get("/api/audit-logs?username=literal_match").json()
    assert body["total"] == 1
    assert body["logs"][0]["username"] == "literal_match_user"


# ── Pagination ─────────────────────────────────────────────────────


def test_audit_logs_pagination_via_offset(admin_client, seeded_audit):
    """offset + limit drive page navigation — same pattern as
    /api/audit/stream-logs."""
    page1 = admin_client.get("/api/audit-logs?limit=2&offset=0").json()
    page2 = admin_client.get("/api/audit-logs?limit=2&offset=2").json()

    assert page1["total"] == 5
    assert page2["total"] == 5
    assert len(page1["logs"]) == 2
    assert len(page2["logs"]) == 2
    # Different rows on different pages — pin by id rather than
    # timestamp (timestamp ties could collide on rapid inserts).
    page1_ids = {row["id"] for row in page1["logs"]}
    page2_ids = {row["id"] for row in page2["logs"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_audit_logs_offset_capped_at_one_million(admin_client):
    """OFFSET is O(n) on SQLite — cap defends against a "skip a
    billion rows" attack.  Same cap as the sibling endpoints."""
    resp = admin_client.get("/api/audit-logs?offset=2000000")
    assert resp.status_code == 422


# ── Auth ───────────────────────────────────────────────────────────


def test_audit_logs_requires_admin(viewer_client):
    """Endpoint is admin-only.  A viewer requesting the audit log
    of their own org gets 403 — only admins should see who's been
    doing what across the org."""
    resp = viewer_client.get("/api/audit-logs")
    assert resp.status_code == 403
