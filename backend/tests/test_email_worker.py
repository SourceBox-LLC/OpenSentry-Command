"""
Tests for the email worker (app/core/email_worker.py).

These exercise the worker in isolation — call ``run_one_tick(db)``
directly, bypassing the asyncio loop, so the assertions are
deterministic and don't depend on sleep timing.

The Resend transport is monkeypatched at the ``email_worker.send_email``
binding (NOT the module the worker imports from) so we don't need to
poke the resend SDK itself.  This keeps the tests focused on the
worker's own state machine: pending → sending → {sent | suppressed |
failed | back-to-pending} → log row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core import email_worker
from app.core.email import EmailSendResult
from app.models.models import EmailLog, EmailOutbox, EmailSuppression

# ── Test fixtures ────────────────────────────────────────────────────

def _make_outbox_row(
    db,
    *,
    org_id: str = "org_test",
    recipient: str = "alice@example.com",
    kind: str = "camera_offline",
    status: str = "pending",
    attempts: int = 0,
    last_attempt_at=None,
) -> EmailOutbox:
    row = EmailOutbox(
        org_id=org_id,
        recipient_email=recipient,
        subject=f"{kind} alert",
        body_text="plain body",
        body_html="<p>html body</p>",
        kind=kind,
        status=status,
        attempts=attempts,
        last_attempt_at=last_attempt_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def stub_send(monkeypatch):
    """Yields a controllable stub for the transport.

    Tests configure ``stub.next_results`` (list of EmailSendResult to
    return in order) and read ``stub.calls`` (list of recipient
    addresses Resend was asked to send to).
    """
    class Stub:
        def __init__(self):
            self.next_results: list[EmailSendResult] = []
            self.default = EmailSendResult(ok=True, message_id="msg_default")
            self.calls: list[dict] = []

        def __call__(self, *, to, subject, body_text, body_html, kind, idempotency_key=None):
            self.calls.append({
                "to": to,
                "subject": subject,
                "kind": kind,
                "idempotency_key": idempotency_key,
            })
            if self.next_results:
                return self.next_results.pop(0)
            return self.default

    stub = Stub()
    monkeypatch.setattr(email_worker, "send_email", stub)
    return stub


# ── Happy path ──────────────────────────────────────────────────────

def test_worker_drains_pending_outbox(db, stub_send):
    """Three pending rows → all three sent in one tick, Resend called
    three times, all rows flipped to status='sent'."""
    rows = [
        _make_outbox_row(db, recipient=f"user{i}@example.com")
        for i in range(3)
    ]
    stub_send.next_results = [
        EmailSendResult(ok=True, message_id=f"msg_{i}") for i in range(3)
    ]

    summary = email_worker.run_one_tick(db)

    assert summary["sent"] == 3
    assert summary["failed"] == 0
    assert summary["suppressed"] == 0
    assert len(stub_send.calls) == 3

    for i, row in enumerate(rows):
        db.refresh(row)
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.resend_message_id == f"msg_{i}"
        assert row.sent_at is not None
        assert row.error is None


def test_worker_writes_log_on_sent(db, stub_send):
    """Each terminal outcome writes one EmailLog row."""
    _make_outbox_row(db, recipient="alice@example.com", kind="camera_offline")
    email_worker.run_one_tick(db)

    logs = db.query(EmailLog).all()
    assert len(logs) == 1
    assert logs[0].status == "sent"
    assert logs[0].recipient_email == "alice@example.com"
    assert logs[0].kind == "camera_offline"
    assert logs[0].resend_message_id == "msg_default"


def test_worker_orders_by_created_at(db, stub_send):
    """Older rows process first.  Otherwise a busy hour of new
    notifications could starve out an older 'camera offline' alert
    that the operator actually needs to see."""
    older = _make_outbox_row(db, recipient="old@example.com")
    # Force an explicit older timestamp — SQLite default-resolution
    # can collide on rapid inserts.
    older.created_at = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(seconds=30)
    db.commit()
    # Side-effect insert; the row is identified by recipient below.
    _make_outbox_row(db, recipient="new@example.com")

    email_worker.run_one_tick(db)

    # The first call should be the older row.
    assert stub_send.calls[0]["to"] == "old@example.com"
    assert stub_send.calls[1]["to"] == "new@example.com"


def test_worker_passes_idempotency_key_per_row(db, stub_send):
    """Each row gets a stable idempotency key derived from its id —
    so a retry of the SAME row doesn't double-send if the previous
    attempt actually succeeded but the response was lost.

    Two different rows must get DIFFERENT keys so they're treated
    as separate sends by Resend."""
    row_a = _make_outbox_row(db, recipient="a@x.test")
    row_b = _make_outbox_row(db, recipient="b@x.test")

    email_worker.run_one_tick(db)

    keys = {c["idempotency_key"] for c in stub_send.calls}
    assert keys == {f"outbox-{row_a.id}", f"outbox-{row_b.id}"}


# ── Suppression ─────────────────────────────────────────────────────

def test_worker_skips_suppressed_addresses(db, stub_send):
    """An address in EmailSuppression must short-circuit BEFORE the
    Resend call (saves a round-trip; protects deliverability rep)."""
    db.add(EmailSuppression(
        address="bouncer@example.com",
        reason="bounce",
        source="resend_webhook",
    ))
    db.commit()

    row = _make_outbox_row(db, recipient="bouncer@example.com")

    summary = email_worker.run_one_tick(db)

    assert summary["suppressed"] == 1
    assert summary["sent"] == 0
    assert len(stub_send.calls) == 0  # Resend was NOT called

    db.refresh(row)
    assert row.status == "suppressed"
    assert "address_suppressed" in (row.error or "")
    assert "reason=bounce" in (row.error or "")


def test_worker_suppression_check_is_case_insensitive(db, stub_send):
    """User adds 'Alice@Example.com' to outbox; suppression has
    'alice@example.com' lowercase.  Must still suppress — otherwise
    the case-insensitive nature of email forces every site to
    canonicalise both sides separately."""
    db.add(EmailSuppression(
        address="alice@example.com",
        reason="complaint",
        source="resend_webhook",
    ))
    db.commit()
    row = _make_outbox_row(db, recipient="Alice@Example.com")

    email_worker.run_one_tick(db)

    db.refresh(row)
    assert row.status == "suppressed"
    assert len(stub_send.calls) == 0


def test_worker_logs_suppressed_outcomes(db, stub_send):
    """Audit trail must capture suppressed sends — useful for
    debugging 'why didn't I get the email' tickets."""
    db.add(EmailSuppression(address="x@y.test", reason="bounce", source="resend_webhook"))
    db.commit()
    _make_outbox_row(db, recipient="x@y.test")

    email_worker.run_one_tick(db)

    logs = db.query(EmailLog).all()
    assert len(logs) == 1
    assert logs[0].status == "suppressed"


# ── Retry / failure ─────────────────────────────────────────────────

def test_worker_retries_on_transient_failure(db, stub_send, monkeypatch):
    """First attempt fails → row stays 'pending' with attempts=1.
    Second tick succeeds → row flips to 'sent' with attempts=2.

    Also pins the summary-counts contract: a row that retries
    before succeeding shows up as sent=1 in the tick that actually
    succeeded, NOT as failed=1 + sent=1 across both ticks.  The
    summary line is what hits operator log streams; counting per-
    attempt would falsely imply more failures than actually
    happened to anyone reading the steady-state log."""
    # Make sure MAX_ATTEMPTS is high enough.
    monkeypatch.setattr(email_worker.settings, "EMAIL_MAX_ATTEMPTS", 3)

    row = _make_outbox_row(db, recipient="alice@example.com")
    stub_send.next_results = [
        EmailSendResult(ok=False, error="ConnectionError: timeout"),
        EmailSendResult(ok=True, message_id="msg_retry"),
    ]

    # Tick 1: fails — row stays pending, summary counts NOTHING
    # (mid-retry isn't a terminal outcome).
    summary1 = email_worker.run_one_tick(db)
    db.refresh(row)
    assert row.status == "pending"
    assert row.attempts == 1
    assert "ConnectionError" in (row.error or "")
    assert summary1.get("failed", 0) == 0  # not yet a terminal failure
    assert summary1.get("sent", 0) == 0

    # Tick 2: succeeds — summary now reports the eventual outcome.
    summary2 = email_worker.run_one_tick(db)
    db.refresh(row)
    assert row.status == "sent"
    assert row.attempts == 2
    assert row.resend_message_id == "msg_retry"
    assert row.error is None
    assert summary2["sent"] == 1
    assert summary2.get("failed", 0) == 0


def test_worker_gives_up_at_max_attempts(db, stub_send, monkeypatch):
    """After EMAIL_MAX_ATTEMPTS failures, row is marked 'failed'
    permanently — no more retries for that row.

    Summary contract: only the FINAL tick (which marks the row
    terminally failed) increments summary['failed']; the prior
    two failed-but-retrying ticks count nothing."""
    monkeypatch.setattr(email_worker.settings, "EMAIL_MAX_ATTEMPTS", 3)

    row = _make_outbox_row(db, recipient="alice@example.com")
    stub_send.default = EmailSendResult(ok=False, error="HTTP 500")

    summaries = []
    for _ in range(3):
        summaries.append(email_worker.run_one_tick(db))
        db.refresh(row)

    assert row.status == "failed"
    assert row.attempts == 3
    assert row.error == "HTTP 500"

    # Ticks 1 + 2 produced no terminal counts; tick 3 produced one
    # terminal failure.  Total across all ticks: failed=1, NOT failed=3.
    total_failed = sum(s.get("failed", 0) for s in summaries)
    assert total_failed == 1, (
        f"expected 1 terminal failure across all ticks, got {total_failed} "
        f"(per-tick: {[s.get('failed', 0) for s in summaries]})"
    )

    # Fourth tick should pick up nothing — row is no longer 'pending'.
    stub_send.calls.clear()
    email_worker.run_one_tick(db)
    assert len(stub_send.calls) == 0


def test_worker_only_logs_terminal_failures(db, stub_send, monkeypatch):
    """Mid-retry failures (status flips back to 'pending') must NOT
    write an EmailLog row — would flood the audit trail with one row
    per attempt instead of one per outcome."""
    monkeypatch.setattr(email_worker.settings, "EMAIL_MAX_ATTEMPTS", 3)

    _make_outbox_row(db, recipient="alice@example.com")
    stub_send.default = EmailSendResult(ok=False, error="HTTP 500")

    # Tick 1: should NOT log (still retrying).
    email_worker.run_one_tick(db)
    assert db.query(EmailLog).count() == 0

    # Tick 2: still retrying → no log.
    email_worker.run_one_tick(db)
    assert db.query(EmailLog).count() == 0

    # Tick 3: terminal failure → ONE log.
    email_worker.run_one_tick(db)
    logs = db.query(EmailLog).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].error == "HTTP 500"


# ── Reclaim stuck 'sending' rows ─────────────────────────────────────

def test_worker_reclaims_stuck_sending_rows(db, stub_send):
    """A row stuck in 'sending' for >60s (worker died mid-flight)
    gets flipped back to 'pending' and re-processed on the next tick.
    Resend's idempotency-key header (set in core/email.py) ensures we
    don't double-send if the original attempt actually succeeded."""
    old = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(seconds=120)
    row = _make_outbox_row(
        db, recipient="alice@example.com",
        status="sending", last_attempt_at=old,
    )

    summary = email_worker.run_one_tick(db)

    assert summary["reclaimed"] == 1
    assert summary["sent"] == 1  # got reclaimed AND processed in same tick
    db.refresh(row)
    assert row.status == "sent"


def test_worker_does_not_reclaim_recently_claimed_rows(db, stub_send):
    """A row flipped to 'sending' 5 seconds ago must NOT be
    reclaimed — the worker that claimed it could still be in-flight,
    and reclaiming would cause a true duplicate send."""
    recent = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(seconds=5)
    row = _make_outbox_row(
        db, recipient="alice@example.com",
        status="sending", last_attempt_at=recent,
    )

    summary = email_worker.run_one_tick(db)

    assert summary["reclaimed"] == 0
    db.refresh(row)
    assert row.status == "sending"  # left alone


# ── Empty queue ─────────────────────────────────────────────────────

def test_worker_no_op_on_empty_queue(db, stub_send):
    """No pending rows → no Resend calls, no log writes, summary
    reports zeros.  Important: the worker runs every 5s in production,
    so this is the steady-state hot path — must be cheap and silent."""
    summary = email_worker.run_one_tick(db)

    assert summary == {"sent": 0, "failed": 0, "suppressed": 0, "reclaimed": 0}
    assert len(stub_send.calls) == 0
    assert db.query(EmailLog).count() == 0
