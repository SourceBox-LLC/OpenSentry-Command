"""
Tests for unsubscribe-token sign/verify (app/core/email_unsubscribe.py).

Token shape and lifecycle:
  - signed JWT with HS256 + CLERK_SECRET_KEY
  - payload: {org_id, kind, iat, sub: 'email-unsubscribe'}
  - never expires (CAN-SPAM requires links to remain functional;
    expiring would defeat the point)

These tests verify both happy path and the failure modes that
matter — bad signature, wrong subject claim (defends future tokens
signed with the same key), missing claims, malformed token strings.
"""

from __future__ import annotations

import jwt
import pytest

from app.core import email_unsubscribe


# ── Round-trip ──────────────────────────────────────────────────────

def test_make_and_verify_token_roundtrip():
    """Sign then verify the same token returns the original claims."""
    token = email_unsubscribe.make_token("org_abc", "camera_offline")

    decoded = email_unsubscribe.verify_token(token)

    assert decoded == ("org_abc", "camera_offline")


def test_token_carries_correct_subject_claim():
    """Subject claim is 'email-unsubscribe' — used by verify_token to
    refuse other JWTs signed with the same key.  Pin it so a refactor
    that changes the value also surfaces here."""
    token = email_unsubscribe.make_token("org_x", "node_offline")
    raw = jwt.decode(token, options={"verify_signature": False})
    assert raw["sub"] == "email-unsubscribe"
    assert raw["org_id"] == "org_x"
    assert raw["kind"] == "node_offline"
    assert "iat" in raw  # issued-at present for audit


# ── Verification failure modes ──────────────────────────────────────

def test_verify_rejects_bad_signature(monkeypatch):
    """Token signed with a different secret must NOT verify."""
    # Sign with a wrong key.
    fake = jwt.encode(
        {"org_id": "x", "kind": "camera_offline", "sub": "email-unsubscribe"},
        "wrong-secret",
        algorithm="HS256",
    )

    decoded = email_unsubscribe.verify_token(fake)

    assert decoded is None


def test_verify_rejects_wrong_subject_claim():
    """A JWT with the right signature but a different 'sub' claim
    must be refused — defends against future tokens signed with the
    same key being abused as unsubscribe links."""
    secret = email_unsubscribe._get_secret()
    fake = jwt.encode(
        {"org_id": "x", "kind": "camera_offline", "sub": "session"},
        secret,
        algorithm="HS256",
    )

    decoded = email_unsubscribe.verify_token(fake)

    assert decoded is None


def test_verify_rejects_missing_org_id():
    """Token without org_id can't be acted on."""
    secret = email_unsubscribe._get_secret()
    fake = jwt.encode(
        {"kind": "camera_offline", "sub": "email-unsubscribe"},
        secret,
        algorithm="HS256",
    )

    decoded = email_unsubscribe.verify_token(fake)

    assert decoded is None


def test_verify_rejects_missing_kind():
    """Token without kind can't be acted on either."""
    secret = email_unsubscribe._get_secret()
    fake = jwt.encode(
        {"org_id": "x", "sub": "email-unsubscribe"},
        secret,
        algorithm="HS256",
    )

    decoded = email_unsubscribe.verify_token(fake)

    assert decoded is None


@pytest.mark.parametrize("bad", ["", None, "not-a-jwt", "a.b.c", 12345])
def test_verify_rejects_malformed_input(bad):
    """Random garbage in the URL parameter doesn't crash — returns None."""
    decoded = email_unsubscribe.verify_token(bad)
    assert decoded is None


# ── URL construction ────────────────────────────────────────────────

def test_build_unsubscribe_url_includes_token(monkeypatch):
    """Full URL: <frontend>/api/notifications/email/unsubscribe?t=<token>"""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "FRONTEND_URL", "https://app.test")

    url = email_unsubscribe.build_unsubscribe_url("org_x", "camera_offline")

    assert url.startswith("https://app.test/api/notifications/email/unsubscribe?t=")
    # The token portion must round-trip.
    token = url.split("?t=")[1]
    assert email_unsubscribe.verify_token(token) == ("org_x", "camera_offline")


def test_build_unsubscribe_url_strips_trailing_slash(monkeypatch):
    """FRONTEND_URL with a trailing slash shouldn't produce a //
    in the path — looks broken in email previews."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "FRONTEND_URL", "https://app.test/")

    url = email_unsubscribe.build_unsubscribe_url("org_x", "camera_offline")

    assert "//api" not in url
    assert "/api/notifications" in url
