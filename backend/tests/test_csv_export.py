"""
Tests for the CSV export path on the three audit-log endpoints.

Pinned invariants:

  1. ``?format=csv`` flips the response to text/csv with a sane
     Content-Disposition filename (so browsers actually download
     instead of rendering inline as text).
  2. The header row matches the documented column order.  Frontend
     code + downstream spreadsheet templates should be safe assuming
     stable column positions.
  3. Org isolation still applies — a CSV export only contains rows
     belonging to the caller's org.  This is the highest-impact
     test in the file: a regression here would leak audit data
     across tenants.
  4. Filters apply to the CSV query the same as they do to JSON
     (camera_id, user_id on stream-logs; tool_name on mcp logs).
  5. Auth + rate limit still enforced.
  6. The streaming generator survives an empty result (header-only
     CSV is a valid response, not an error).
  7. CSV escapes embedded commas and quotes correctly so a malicious
     ``details`` field can't break parsing.

The shared helper itself (``app.core.csv_export``) is exercised
indirectly via every endpoint test; we don't unit-test the helper
in isolation because its only consumer is these three endpoints
and the integration tests are more useful as regression catches.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.models.models import AuditLog, McpActivityLog, StreamAccessLog

# ── Helpers ─────────────────────────────────────────────────────────


def _parse_csv(body: str) -> list[list[str]]:
    """Parse a CSV response body into a list of rows."""
    return list(csv.reader(io.StringIO(body)))


# ── /api/audit-logs CSV ─────────────────────────────────────────────


def test_audit_logs_csv_returns_text_csv(admin_client, db):
    """Smoke test: ``?format=csv`` flips media type + sets a
    Content-Disposition that triggers a browser download."""
    db.add(AuditLog(
        org_id="org_test123",
        timestamp=datetime.now(tz=UTC).replace(tzinfo=None),
        event="member_added",
        username="alice@example.com",
        user_id="user_alice",
        ip_address="10.0.0.1",
        details="role=admin",
    ))
    db.commit()

    resp = admin_client.get("/api/audit-logs?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    # Filename includes the org id so multi-org auditors can tell
    # exports apart at a glance.
    assert "org_test123" in resp.headers["content-disposition"]
    # Must NOT cache — audit logs are sensitive + per-tenant.
    assert resp.headers.get("cache-control") == "no-store"


def test_audit_logs_csv_header_matches_documented_columns(admin_client):
    """Header row pin: column order is documented elsewhere (in the
    endpoint docstring + this test).  A reorder breaks every
    spreadsheet template a customer has built on top of the export."""
    resp = admin_client.get("/api/audit-logs?format=csv")
    rows = _parse_csv(resp.text)

    assert len(rows) >= 1
    assert rows[0] == [
        "timestamp", "event", "username", "user_id", "ip_address", "details",
    ]


def test_audit_logs_csv_org_isolation(admin_client, db):
    """A CSV export must contain ONLY rows from the caller's org.
    A regression here = cross-tenant audit-log leak = catastrophic."""
    # Seed rows in two different orgs.
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add(AuditLog(
        org_id="org_test123",  # caller's org
        timestamp=now,
        event="member_added",
        username="ours@example.com",
    ))
    db.add(AuditLog(
        org_id="org_OTHER999",  # different org — must NOT leak
        timestamp=now,
        event="member_added",
        username="theirs@example.com",
    ))
    db.commit()

    resp = admin_client.get("/api/audit-logs?format=csv")
    rows = _parse_csv(resp.text)
    body_text = resp.text

    # Our row appears.
    assert any("ours@example.com" in r for r in rows[1:])
    # Their row does NOT.
    assert "theirs@example.com" not in body_text


def test_audit_logs_csv_escapes_special_chars(admin_client, db):
    """A malicious or operator-named ``details`` containing commas /
    quotes / newlines must not break CSV parsing."""
    db.add(AuditLog(
        org_id="org_test123",
        timestamp=datetime.now(tz=UTC).replace(tzinfo=None),
        event="settings_changed",
        details='comma, quote " and\nnewline embedded',
    ))
    db.commit()

    resp = admin_client.get("/api/audit-logs?format=csv")
    rows = _parse_csv(resp.text)
    # csv.reader successfully parsed it — confirm the original details
    # made it back through the round-trip intact.
    matching = [r for r in rows if 'comma, quote' in (r[5] if len(r) > 5 else "")]
    assert len(matching) == 1
    assert 'comma, quote " and\nnewline embedded' == matching[0][5]


def test_audit_logs_csv_returns_header_only_on_empty(admin_client):
    """Zero rows must produce a valid CSV with just the header.
    A 200-with-empty-body would confuse spreadsheet importers."""
    resp = admin_client.get("/api/audit-logs?format=csv")
    rows = _parse_csv(resp.text)
    assert len(rows) == 1
    assert rows[0][0] == "timestamp"


def test_audit_logs_csv_requires_admin(viewer_client):
    """The JSON endpoint is admin-only; the CSV branch must be too.
    A regression that gated only on the JSON path's auth would let
    viewers exfiltrate the entire audit log via the new CSV path."""
    resp = viewer_client.get("/api/audit-logs?format=csv")
    assert resp.status_code == 403


def test_audit_logs_csv_invalid_format_rejected(admin_client):
    """``?format=xml`` (or any non-{json,csv}) should 422 from the
    pattern guard rather than silently fall through to JSON."""
    resp = admin_client.get("/api/audit-logs?format=xml")
    assert resp.status_code == 422


# ── /api/audit/stream-logs CSV ──────────────────────────────────────


def test_stream_logs_csv_header_matches_documented_columns(admin_client):
    """Same column-order guarantee for the stream-access CSV."""
    resp = admin_client.get("/api/audit/stream-logs?format=csv")
    rows = _parse_csv(resp.text)
    assert rows[0] == [
        "accessed_at", "camera_id", "node_id", "user_email", "user_id", "ip_address",
    ]


def test_stream_logs_csv_filters_apply(admin_client, db):
    """Filters that work on the JSON path must apply to CSV too,
    so an auditor's "show me only what user X did" CSV doesn't
    silently include other users."""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add(StreamAccessLog(
        user_id="user_alice", user_email="alice@example.com",
        org_id="org_test123", camera_id="cam_front", node_id="node_1",
        accessed_at=now,
    ))
    db.add(StreamAccessLog(
        user_id="user_bob", user_email="bob@example.com",
        org_id="org_test123", camera_id="cam_back", node_id="node_1",
        accessed_at=now,
    ))
    db.commit()

    # Filter to a single camera — only that camera's row should appear.
    resp = admin_client.get("/api/audit/stream-logs?format=csv&camera_id=cam_front")
    rows = _parse_csv(resp.text)
    data_rows = rows[1:]
    assert len(data_rows) == 1
    assert data_rows[0][1] == "cam_front"


def test_stream_logs_csv_org_isolation(admin_client, db):
    """Same org-isolation guarantee as audit-logs.  Pin per-endpoint
    because each endpoint applies the org filter independently."""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add(StreamAccessLog(
        user_id="ours", user_email="ours@example.com",
        org_id="org_test123", camera_id="cam_a", node_id="node_a",
        accessed_at=now,
    ))
    db.add(StreamAccessLog(
        user_id="theirs", user_email="theirs@example.com",
        org_id="org_OTHER999", camera_id="cam_b", node_id="node_b",
        accessed_at=now,
    ))
    db.commit()

    resp = admin_client.get("/api/audit/stream-logs?format=csv")
    body = resp.text
    assert "ours@example.com" in body
    assert "theirs@example.com" not in body


# ── /api/mcp/activity/logs CSV ──────────────────────────────────────


def test_mcp_logs_csv_header_matches_documented_columns(admin_client):
    """Column-order pin for MCP CSV."""
    resp = admin_client.get("/api/mcp/activity/logs?format=csv")
    rows = _parse_csv(resp.text)
    assert rows[0] == [
        "timestamp", "tool_name", "key_name", "status",
        "duration_ms", "args_summary", "error",
    ]


def test_mcp_logs_csv_filters_apply(admin_client, db):
    """Tool-name filter applies to CSV the same as JSON."""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add(McpActivityLog(
        org_id="org_test123", tool_name="list_cameras",
        key_name="ci_robot", status="ok", duration_ms=42,
        args_summary="{}", timestamp=now,
    ))
    db.add(McpActivityLog(
        org_id="org_test123", tool_name="view_camera",
        key_name="ci_robot", status="ok", duration_ms=120,
        args_summary='{"camera_id":"cam1"}', timestamp=now,
    ))
    db.commit()

    resp = admin_client.get(
        "/api/mcp/activity/logs?format=csv&tool_name=view_camera"
    )
    rows = _parse_csv(resp.text)
    data_rows = rows[1:]
    assert len(data_rows) == 1
    assert data_rows[0][1] == "view_camera"


def test_mcp_logs_csv_org_isolation(admin_client, db):
    """Same org-isolation pin for MCP."""
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    db.add(McpActivityLog(
        org_id="org_test123", tool_name="list_cameras",
        key_name="ours", status="ok", duration_ms=10, timestamp=now,
    ))
    db.add(McpActivityLog(
        org_id="org_OTHER999", tool_name="list_cameras",
        key_name="theirs", status="ok", duration_ms=10, timestamp=now,
    ))
    db.commit()

    resp = admin_client.get("/api/mcp/activity/logs?format=csv")
    body = resp.text
    assert "ours" in body
    assert "theirs" not in body


# ── Cross-cutting: rate-limit still applies on CSV path ────────────


def test_csv_export_counted_against_rate_limit(admin_client):
    """The JSON path is capped at 120/min per org; the CSV branch
    runs in the same handler so it MUST count against the same
    bucket.  Without this, an attacker could flip ``?format=csv``
    to bypass the JSON rate limit entirely."""
    # Both formats share the same @limiter.limit("120/minute") on
    # /api/audit-logs.  Hammer the endpoint mixing both formats and
    # confirm the bucket still trips at 120 total.
    for i in range(120):
        # Alternate JSON / CSV so neither format alone would hit 120.
        path = "/api/audit-logs" if i % 2 == 0 else "/api/audit-logs?format=csv"
        r = admin_client.get(path)
        assert r.status_code == 200, f"req #{i + 1}: {r.status_code}"

    overflow = admin_client.get("/api/audit-logs?format=csv")
    assert overflow.status_code == 429
    assert overflow.json().get("error") == "rate_limit_exceeded"
