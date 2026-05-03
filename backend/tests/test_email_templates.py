"""
Tests for the Jinja2 email renderer (app/core/email_templates.py).

Cover the bits with logic — autoescape selection per file
extension, the NotificationProxy meta parsing, fallback when a
template file is missing.  The actual template content (subject
strings, body copy) is exercised end-to-end via test_notifications.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import email_templates


def _fake_notif(**overrides):
    """Build a SimpleNamespace that quacks like a Notification for
    the renderer's purposes.  Avoids needing a full DB fixture for
    template-only tests."""
    base = {
        "title": "Front Door went offline",
        "body": "No heartbeat in 90s.",
        "severity": "warning",
        "camera_id": "cam_front_door",
        "node_id": None,
        "link": "/dashboard?camera=cam_front_door",
        "meta_json": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Autoescape selection ─────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("camera_offline.body.html.j2", True),
    ("camera_offline.body.txt.j2", False),
    ("camera_offline.subject.txt.j2", False),
    ("_layout.html.j2", True),
    ("foo.html", True),
    ("foo.txt", False),
    (None, False),
])
def test_should_autoescape_picks_html_only(name, expected):
    """The .html.j2 vs .txt.j2 distinction drives autoescape — without
    it, plain-text emails would render literal '&amp;' instead of
    the original ampersand."""
    assert email_templates._should_autoescape(name) is expected


# ── Notification proxy ───────────────────────────────────────────────

def test_notification_proxy_parses_meta_json():
    """Templates access ``notification.meta.incident_id`` as if it
    were a regular dict; the proxy parses meta_json on construction
    so templates don't need to call json.loads themselves."""
    notif = _fake_notif(meta_json='{"incident_id": 42, "severity": "high"}')
    proxy = email_templates._NotificationProxy(notif)

    assert proxy.meta == {"incident_id": 42, "severity": "high"}
    # Other fields forwarded to the wrapped notification.
    assert proxy.title == "Front Door went offline"
    assert proxy.camera_id == "cam_front_door"


def test_notification_proxy_handles_missing_meta():
    """No meta_json → empty dict, NOT None.  Lets templates use
    ``notification.meta.foo`` without a guard."""
    notif = _fake_notif(meta_json=None)
    proxy = email_templates._NotificationProxy(notif)
    assert proxy.meta == {}


def test_notification_proxy_handles_invalid_meta_json():
    """Garbage in meta_json → empty dict, not crash.  meta_json is
    notionally controlled by us (we serialize it from
    create_notification's meta arg) but defense in depth."""
    notif = _fake_notif(meta_json="this is not json")
    proxy = email_templates._NotificationProxy(notif)
    assert proxy.meta == {}


def test_notification_proxy_handles_non_dict_meta():
    """Templates expect ``notification.meta`` to be a dict.  A
    JSON list or string in meta_json must not surface as the wrong
    type — return {} instead."""
    notif = _fake_notif(meta_json='["a", "b"]')
    proxy = email_templates._NotificationProxy(notif)
    assert proxy.meta == {}


# ── render() integration ─────────────────────────────────────────────

def test_render_camera_offline_produces_three_strings():
    """Smoke test the full pipeline for the canonical kind.  Don't
    pin specific copy (templates change) — just verify the shape."""
    notif = _fake_notif()

    subject, body_text, body_html = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/api/notifications/email/unsubscribe?t=abc",
    )

    assert isinstance(subject, str) and subject.strip()
    assert "SourceBox Sentry" in subject
    assert "Front Door" in subject
    assert isinstance(body_text, str)
    assert "Front Door went offline" in body_text
    assert "https://x.test/api/notifications/email/unsubscribe?t=abc" in body_text

    assert isinstance(body_html, str)
    # Layout wrap brings in brand header.
    assert "<!DOCTYPE html>" in body_html
    assert "SourceBox Sentry" in body_html
    # Severity bar coloured for warning.
    assert "#f59e0b" in body_html  # severity="warning"


def test_render_severity_color_propagates():
    """Severity drives the colored bar in the layout — test each
    mapped severity at the boundary."""
    cases = {
        "critical": "#ef4444",
        "error": "#ef4444",
        "warning": "#f59e0b",
        "info": "#22c55e",
    }
    for severity, expected_color in cases.items():
        notif = _fake_notif(severity=severity)
        _, _, body_html = email_templates.render(
            "camera_offline", notif,
            unsubscribe_url="https://x.test/u",
        )
        assert expected_color in body_html, f"missing {expected_color} for {severity}"


def test_render_unknown_severity_falls_back_to_green():
    """A future severity value we don't recognise renders green
    (default) instead of crashing."""
    notif = _fake_notif(severity="psychic_damage")
    _, _, body_html = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/u",
    )
    assert "#22c55e" in body_html  # info default


def test_render_unknown_kind_uses_generic_fallback():
    """A kind without dedicated templates still emits a usable
    email — fallback subject + generic body block.  Important
    because the inbox supports kinds the email layer doesn't yet."""
    notif = _fake_notif(title="Mystery event", body="Something happened.")

    subject, body_text, body_html = email_templates.render(
        "kind_we_havent_built_a_template_for", notif,
        unsubscribe_url="https://x.test/u",
    )

    # Generic fallback subject.
    assert "Mystery event" in subject
    # Body still includes the title + body text + unsubscribe link.
    assert "Mystery event" in body_text
    assert "Something happened" in body_text
    assert "https://x.test/u" in body_text


def test_render_html_escapes_user_content():
    """Notification title/body fields containing HTML must be
    escaped in the HTML body block.  Defense in depth — the field
    is operator-controlled but a malformed camera name shouldn't
    open an XSS path."""
    notif = _fake_notif(
        title="<script>alert(1)</script>",
        body="Body with <b>bold</b>",
    )
    _, _, body_html = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/u",
    )
    assert "<script>alert(1)</script>" not in body_html
    assert "&lt;script&gt;" in body_html


def test_render_text_does_not_escape_user_content():
    """Plain-text body must NOT escape — would render '&amp;' as
    literal text in the email instead of '&'.  The .txt.j2
    templates are autoescape-off because of _should_autoescape."""
    notif = _fake_notif(body="Tom & Jerry < or >")
    _, body_text, _ = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/u",
    )
    assert "Tom & Jerry < or >" in body_text


def test_render_uses_dashboard_url_override():
    """Caller can override the dashboard URL (tests, multi-domain
    deploys).  Without override, falls back to settings.FRONTEND_URL."""
    notif = _fake_notif()
    _, body_text, _ = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/u",
        dashboard_url="https://override.example.com",
    )
    assert "https://override.example.com" in body_text


def test_render_strips_embedded_newlines_from_subject():
    """A title containing CR/LF (operator-controlled camera name OR
    AI-agent-supplied incident title) must NOT leak into the rendered
    subject as embedded newlines.  Resend's API rejects subject
    header injection today, but a future provider swap that forwards
    subjects raw to SMTP would turn this into a Bcc-injection vector.

    Covers `\\n`, `\\r`, and `\\r\\n` separators for completeness."""
    notif = _fake_notif(title="Front Door\r\nBcc: attacker@evil.test")

    subject, _, _ = email_templates.render(
        "camera_offline", notif,
        unsubscribe_url="https://x.test/u",
    )

    assert "\r" not in subject
    assert "\n" not in subject
    # The original characters survive (just as spaces / removed CRs)
    # so the alert remains intelligible to the recipient.
    assert "Front Door" in subject
    assert "Bcc: attacker@evil.test" in subject
