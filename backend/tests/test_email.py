"""
Tests for the Resend transport wrapper (app/core/email.py).

These cover the surface every other email path depends on:
  - kill-switch behaviour (EMAIL_ENABLED=false)
  - missing credentials handling
  - success path returns a usable EmailSendResult
  - failure path swallows exceptions and surfaces them in .error
  - redaction strips PII from log output
"""

from __future__ import annotations

import pytest

from app.core import email as email_mod
from app.core.email import EmailSendResult, send_email


# ── Kill-switch ──────────────────────────────────────────────────────

def test_send_email_kill_switch_short_circuits(monkeypatch):
    """EMAIL_ENABLED=false returns ok=True + skipped=True without
    touching Resend.  This is the dev-default — local dev shouldn't
    burn the free-tier daily limit just by booting the app."""
    monkeypatch.setattr(email_mod.settings, "EMAIL_ENABLED", False)

    # Sentinel — if Resend gets called, this test fails because we
    # would have raised AttributeError on the missing api_key.
    called = {"sent": False}
    def boom(*a, **kw):
        called["sent"] = True
        raise AssertionError("Resend should not be called when kill-switch off")
    monkeypatch.setattr(email_mod.resend.Emails, "send", boom)

    result = send_email(
        to="alice@example.com",
        subject="hi",
        body_text="t",
        body_html="<p>t</p>",
        kind="camera_offline",
    )

    assert isinstance(result, EmailSendResult)
    assert result.ok is True
    assert result.skipped is True
    assert result.message_id is None
    assert called["sent"] is False


# ── Missing credentials ─────────────────────────────────────────────

def test_send_email_missing_api_key_returns_unconfigured(monkeypatch):
    """No RESEND_API_KEY should fail fast with a recognisable error
    string — the worker uses this to mark rows 'failed' permanently
    instead of retrying forever against a misconfigured deploy."""
    monkeypatch.setattr(email_mod.settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(email_mod.settings, "RESEND_API_KEY", "")

    result = send_email(
        to="alice@example.com",
        subject="hi",
        body_text="t",
        body_html="<p>t</p>",
        kind="camera_offline",
    )

    assert result.ok is False
    assert result.error is not None
    assert "resend_unconfigured" in result.error


# ── Success path ────────────────────────────────────────────────────

def test_send_email_success_extracts_message_id(monkeypatch):
    """A normal Resend response (dict with 'id') round-trips into
    EmailSendResult.message_id."""
    monkeypatch.setattr(email_mod.settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(email_mod.settings, "RESEND_API_KEY", "re_test_dummy")
    monkeypatch.setattr(email_mod.settings, "EMAIL_FROM_ADDRESS", "n@s.test")

    captured: dict = {}
    def fake_send(payload):
        captured["payload"] = payload
        return {"id": "msg_abc123"}
    monkeypatch.setattr(email_mod.resend.Emails, "send", fake_send)

    result = send_email(
        to="alice@example.com",
        subject="Camera Front Door went offline",
        body_text="Plain",
        body_html="<p>HTML</p>",
        kind="camera_offline",
        idempotency_key="outbox-42",
    )

    assert result.ok is True
    assert result.message_id == "msg_abc123"
    assert result.skipped is False

    # Verify we sent the right shape — tag injection, idempotency
    # header, both body parts.
    p = captured["payload"]
    assert p["to"] == ["alice@example.com"]
    assert p["subject"] == "Camera Front Door went offline"
    assert p["text"] == "Plain"
    assert p["html"] == "<p>HTML</p>"
    assert {"name": "event", "value": "camera_offline"} in p["tags"]
    assert p["headers"]["Idempotency-Key"] == "outbox-42"


def test_send_email_no_message_id_returns_failure(monkeypatch):
    """Resend returning a 200 without an 'id' field is a degraded
    success — without the id we can't correlate webhook events back
    to the outbox row, so we mark the send failed and let the worker
    retry.  Beats silently losing audit trail."""
    monkeypatch.setattr(email_mod.settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(email_mod.settings, "RESEND_API_KEY", "re_test_dummy")

    monkeypatch.setattr(email_mod.resend.Emails, "send", lambda payload: {})

    result = send_email(
        to="alice@example.com",
        subject="x",
        body_text="t",
        body_html="<p>t</p>",
        kind="camera_offline",
    )

    assert result.ok is False
    assert result.error == "resend_no_message_id"


# ── Failure path ────────────────────────────────────────────────────

def test_send_email_swallows_exceptions_into_error(monkeypatch):
    """A network error / Resend 5xx must NOT propagate out of
    send_email — the worker is supposed to catch a clean
    EmailSendResult and decide retry-vs-give-up, not handle a bare
    exception."""
    monkeypatch.setattr(email_mod.settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(email_mod.settings, "RESEND_API_KEY", "re_test_dummy")

    def boom(payload):
        raise ConnectionError("DNS failure")
    monkeypatch.setattr(email_mod.resend.Emails, "send", boom)

    result = send_email(
        to="alice@example.com",
        subject="x",
        body_text="t",
        body_html="<p>t</p>",
        kind="camera_offline",
    )

    assert result.ok is False
    assert result.error is not None
    assert "ConnectionError" in result.error
    assert "DNS failure" in result.error


# ── Redaction ───────────────────────────────────────────────────────

@pytest.mark.parametrize("addr,expected", [
    ("alice@example.com", "a***@example.com"),
    ("bob.smith@company.co.uk", "b***@company.co.uk"),
    ("@malformed.com", "***@malformed.com"),
    ("no-at-sign", "***"),
    ("", "***"),
])
def test_redact_masks_local_part(addr, expected):
    """Log lines must include enough of the address to disambiguate
    in support tickets but NOT the full local part — Sentry events
    shouldn't carry user PII verbatim."""
    assert email_mod._redact(addr) == expected
