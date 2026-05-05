"""
Tests for the Resend webhook handler (POST /api/webhooks/resend).

Covers HMAC verification, idempotency dedup, and the bounce/complaint
→ EmailSuppression dispatch.  Real Resend webhooks sign requests via
Svix; the tests build the signing headers using the same Webhook
class so we exercise the actual verification path, not a mock.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timezone

import pytest
from svix.webhooks import Webhook

from app.models.models import (
    EmailOutbox,
    EmailSuppression,
    ProcessedWebhook,
)

# ── Helpers ──────────────────────────────────────────────────────────

# Svix expects a base64-encoded signing secret prefixed with `whsec_`.
# This dummy string is just enough bytes for the library to accept it.
_TEST_SECRET = "whsec_dGVzdC1zZWNyZXQtMTIzNDU2Nzg5MDEyMzQ1Ng=="


def _signed_request(client, secret, payload):
    """Build a Resend-shaped signed POST and return the response.

    ``Webhook.sign`` takes a datetime (not an int) per the standard-
    webhooks reference impl, even though the wire header is an
    integer Unix timestamp."""
    body = json.dumps(payload).encode("utf-8")
    msg_id = f"msg_{uuid.uuid4().hex}"
    timestamp_dt = datetime.now(tz=UTC)
    timestamp_int = int(timestamp_dt.timestamp())
    wh = Webhook(secret)
    signature = wh.sign(msg_id, timestamp_dt, body.decode("utf-8"))

    resp = client.post(
        "/api/webhooks/resend",
        content=body,
        headers={
            "svix-id": msg_id,
            "svix-timestamp": str(timestamp_int),
            "svix-signature": signature,
            "content-type": "application/json",
        },
    )
    return resp, msg_id


@pytest.fixture
def configured_secret(monkeypatch):
    """Set the webhook secret for tests that need verification to pass."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "RESEND_WEBHOOK_SECRET", _TEST_SECRET)
    return _TEST_SECRET


# ── HMAC verification ───────────────────────────────────────────────

def test_resend_webhook_invalid_signature_returns_400(unauthenticated_client, configured_secret):
    """Tamper-detected payload must be rejected with 400.  Without
    this, an attacker who knows the URL but not the secret could
    forge bounce events to suppress legitimate users."""
    body = json.dumps({"type": "email.bounced", "data": {"to": "x@y.test"}}).encode()

    resp = unauthenticated_client.post(
        "/api/webhooks/resend",
        content=body,
        headers={
            "svix-id": f"msg_{uuid.uuid4().hex}",
            "svix-timestamp": str(int(time.time())),
            # Wrong signature.
            "svix-signature": "v1,0000000000000000000000000000000000000000000=",
            "content-type": "application/json",
        },
    )

    assert resp.status_code == 400


def test_resend_webhook_missing_secret_returns_400(unauthenticated_client, monkeypatch):
    """Server with no RESEND_WEBHOOK_SECRET set must reject every
    incoming webhook — better to drop legitimate events than to
    process unsigned ones (which would be unverifiable)."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "RESEND_WEBHOOK_SECRET", "")

    body = json.dumps({"type": "email.bounced"}).encode()
    resp = unauthenticated_client.post(
        "/api/webhooks/resend",
        content=body,
        headers={
            "svix-id": "msg_x",
            "svix-timestamp": str(int(time.time())),
            "svix-signature": "v1,whatever",
            "content-type": "application/json",
        },
    )

    assert resp.status_code == 400


# ── Bounce + complaint → suppression ─────────────────────────────────

def test_resend_webhook_bounced_inserts_suppression(
    unauthenticated_client, db, configured_secret,
):
    """Resend tells us an address bounced → row in EmailSuppression
    so the worker stops sending to it."""
    payload = {
        "type": "email.bounced",
        "data": {
            "email_id": "msg_resend_abc",
            "to": ["bouncer@example.com"],
        },
        "created_at": "2026-05-02T12:00:00Z",
    }

    resp, _ = _signed_request(unauthenticated_client, _TEST_SECRET, payload)
    assert resp.status_code == 200

    rows = db.query(EmailSuppression).all()
    assert len(rows) == 1
    assert rows[0].address == "bouncer@example.com"
    assert rows[0].reason == "bounce"
    assert rows[0].source == "resend_webhook"


def test_resend_webhook_complained_inserts_suppression(
    unauthenticated_client, db, configured_secret,
):
    """User clicked "spam" in their client → suppress with reason='complaint'."""
    payload = {
        "type": "email.complained",
        "data": {
            "email_id": "msg_resend_xyz",
            "to": ["spammer-marker@example.com"],
        },
    }

    resp, _ = _signed_request(unauthenticated_client, _TEST_SECRET, payload)
    assert resp.status_code == 200

    row = db.query(EmailSuppression).first()
    assert row is not None
    assert row.address == "spammer-marker@example.com"
    assert row.reason == "complaint"


def test_resend_webhook_lowercases_address(
    unauthenticated_client, db, configured_secret,
):
    """Suppression address normalised to lowercase so the worker's
    case-insensitive check matches reliably regardless of how the
    user originally signed up ('Alice@Example.com' vs 'alice@…')."""
    payload = {
        "type": "email.bounced",
        "data": {"email_id": "x", "to": ["MIXED@Case.Test"]},
    }

    _signed_request(unauthenticated_client, _TEST_SECRET, payload)

    row = db.query(EmailSuppression).first()
    assert row.address == "mixed@case.test"


def test_resend_webhook_handles_string_to_field(
    unauthenticated_client, db, configured_secret,
):
    """Resend's payload sometimes has ``to`` as a string instead of
    a list — handle both shapes."""
    payload = {
        "type": "email.bounced",
        "data": {"email_id": "x", "to": "single-string@example.com"},
    }

    _signed_request(unauthenticated_client, _TEST_SECRET, payload)

    row = db.query(EmailSuppression).first()
    assert row.address == "single-string@example.com"


def test_resend_webhook_marks_outbox_row_suppressed(
    unauthenticated_client, db, configured_secret,
):
    """A bounced send's outbox row gets flipped from 'sent' to
    'suppressed' so the dashboard can show "this never made it"
    instead of a misleading 'sent' status."""
    db.add(EmailOutbox(
        org_id="org_x",
        recipient_email="bouncer@example.com",
        subject="x",
        body_text="t",
        body_html="<p>t</p>",
        kind="camera_offline",
        status="sent",
        resend_message_id="msg_resend_correlate",
    ))
    db.commit()

    payload = {
        "type": "email.bounced",
        "data": {"email_id": "msg_resend_correlate", "to": ["bouncer@example.com"]},
    }

    _signed_request(unauthenticated_client, _TEST_SECRET, payload)

    row = db.query(EmailOutbox).first()
    assert row.status == "suppressed"
    assert "webhook_event:email.bounced" in (row.error or "")
    assert "reason=bounce" in (row.error or "")


def test_resend_webhook_unknown_event_type_is_accepted(
    unauthenticated_client, db, configured_secret,
):
    """Resend sends opened/clicked/scheduled/etc. events we don't
    handle — must still 200 OK or Resend will eventually disable
    our endpoint for "too many error responses"."""
    payload = {
        "type": "email.opened",
        "data": {"email_id": "x", "to": ["recipient@example.com"]},
    }

    resp, _ = _signed_request(unauthenticated_client, _TEST_SECRET, payload)

    assert resp.status_code == 200
    # No suppression — opened is not a bad event.
    assert db.query(EmailSuppression).count() == 0


# ── Idempotency ─────────────────────────────────────────────────────

def test_resend_webhook_idempotent_replay(
    unauthenticated_client, db, configured_secret,
):
    """Replaying the same signed payload must NOT double-insert
    suppression (or any other side-effect).  Resend retries on any
    non-2xx OR network failure, so we WILL see redeliveries in the
    wild."""
    payload = {
        "type": "email.bounced",
        "data": {"email_id": "x", "to": ["bouncer@example.com"]},
    }

    body = json.dumps(payload).encode()
    msg_id = f"msg_{uuid.uuid4().hex}"
    timestamp_dt = datetime.now(tz=UTC)
    sig = Webhook(_TEST_SECRET).sign(msg_id, timestamp_dt, body.decode("utf-8"))

    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp_dt.timestamp())),
        "svix-signature": sig,
        "content-type": "application/json",
    }

    # First delivery
    r1 = unauthenticated_client.post("/api/webhooks/resend", content=body, headers=headers)
    assert r1.status_code == 200

    # Same delivery again — short-circuits via ProcessedWebhook
    r2 = unauthenticated_client.post("/api/webhooks/resend", content=body, headers=headers)
    assert r2.status_code == 200
    assert r2.json().get("status") == "duplicate"

    # Only ONE suppression row regardless of how many times Resend retries.
    assert db.query(EmailSuppression).count() == 1


def test_resend_webhook_records_processed_id(
    unauthenticated_client, db, configured_secret,
):
    """Each successful delivery writes a ProcessedWebhook row so the
    next retry of the same message can short-circuit."""
    payload = {"type": "email.opened", "data": {"email_id": "x"}}

    resp, msg_id = _signed_request(unauthenticated_client, _TEST_SECRET, payload)
    assert resp.status_code == 200

    row = db.query(ProcessedWebhook).filter_by(svix_msg_id=msg_id).first()
    assert row is not None
    assert row.event_type == "email.opened"
