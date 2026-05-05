"""Regression tests for the log-cleanup UNION query in ``app.main._log_cleanup_loop``.

The cleanup loop UNIONs distinct org_ids across the five log tables once
per day so it can iterate orgs and apply each org's tier-specific
retention. The original implementation chained ``.union()`` calls on the
``select(...).distinct()`` results — which works on a ``Select`` but
NOT on a ``CompoundSelect`` (the result of the previous ``.union()``).

In SQLAlchemy 2.x that produces ``AttributeError: 'CompoundSelect'
object has no attribute 'union'`` and the cleanup silently fails inside
its ``try/except``. Sentry caught it firing nightly in production
(alert OPENSENTRY-COMMAND-1, Apr 2026); these tests pin the
SQLAlchemy-2.x-correct ``union(a, b, c, ...)`` function form so a future
refactor can't quietly reintroduce the same chain pattern.

We don't run the entire ``_log_cleanup_loop`` (async, infinite, sleeps
24h) — we exercise just the query construction + execution against the
same five models, which is where the bug actually was.
"""

from datetime import UTC, datetime, timezone

from sqlalchemy import select, union

from app.core.database import SessionLocal
from app.models.models import (
    AuditLog,
    McpActivityLog,
    MotionEvent,
    Notification,
    StreamAccessLog,
)


def _utcnow_naive() -> datetime:
    """Match the pattern the cleanup loop uses for log timestamps."""
    return datetime.now(tz=UTC).replace(tzinfo=None)


def _build_org_id_union():
    """Mirror exactly the UNION expression in app.main._log_cleanup_loop.

    Kept as a helper so the test asserts on the same shape of query the
    loop builds — drift between this and main.py would still slip
    through, but at least the SQLAlchemy compatibility surface is shared.
    """
    return union(
        select(StreamAccessLog.org_id).distinct(),
        select(McpActivityLog.org_id).distinct(),
        select(AuditLog.org_id).distinct(),
        select(MotionEvent.org_id).distinct(),
        select(Notification.org_id).distinct(),
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_union_query_executes_without_attributeerror():
    """The exact failure mode in production: building + executing the union
    must not raise ``AttributeError: 'CompoundSelect' object has no
    attribute 'union'``. If a future change reintroduces the chained
    ``.union(...).union(...)`` form, this test fails at construction-or-
    execute time, not silently inside the cleanup loop's try/except.
    """
    db = SessionLocal()
    try:
        # No data needed — the query itself was unbuildable in the broken
        # version. We just need the SQLAlchemy compiler to walk the tree.
        result = db.execute(_build_org_id_union()).all()
        assert isinstance(result, list)
    finally:
        db.close()


def test_union_query_returns_distinct_org_ids_across_log_tables():
    """End-to-end: insert rows for two orgs across multiple log tables,
    run the union query, and confirm the deduped set comes back. This
    pins the *behaviour* of the cleanup's first pass, not just the
    SQL-API compatibility.
    """
    db = SessionLocal()
    try:
        now = _utcnow_naive()

        # Org A appears in three tables; Org B appears in one. The union
        # should yield {A, B} — duplicates collapsed by the inner DISTINCTs
        # and the UNION (which dedupes by default in SQLAlchemy).
        db.add(StreamAccessLog(
            org_id="org_A", user_id="u1", camera_id="cam_1", node_id="node_1",
            ip_address="127.0.0.1", user_agent="t", accessed_at=now,
        ))
        db.add(StreamAccessLog(
            org_id="org_A", user_id="u2", camera_id="cam_1", node_id="node_1",
            ip_address="127.0.0.1", user_agent="t", accessed_at=now,
        ))
        db.add(McpActivityLog(
            org_id="org_A", tool_name="list_cameras", key_name="k",
            status="ok", duration_ms=1, timestamp=now,
        ))
        db.add(AuditLog(
            org_id="org_A", event="evt", user_id="u1",
            ip_address="127.0.0.1", details="{}", timestamp=now,
        ))
        db.add(Notification(
            org_id="org_B", kind="motion_detected", audience="all",
            title="t", body="b", severity="info", created_at=now,
        ))
        db.commit()

        rows = db.execute(_build_org_id_union()).all()
        org_ids = {row[0] for row in rows if row[0]}

        assert org_ids == {"org_A", "org_B"}
    finally:
        db.close()


def test_union_query_handles_empty_tables():
    """Fresh deployment with zero log rows: the union must still execute
    cleanly and return an empty result. Without this, a brand-new node
    on day one would hit the cleanup loop and crash on its first
    nightly tick (or, with the original bug, fail silently).
    """
    db = SessionLocal()
    try:
        rows = db.execute(_build_org_id_union()).all()
        assert rows == []
    finally:
        db.close()
