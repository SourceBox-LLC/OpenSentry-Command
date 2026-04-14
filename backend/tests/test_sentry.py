"""Tests for the Sentry init / scrubbing module.

These don't hit sentry.io — they exercise the local control flow:
- no-op when DSN is missing
- init succeeds when DSN is present
- sensitive headers and query strings get scrubbed before ``before_send``
  hands the event to the transport
"""

import os
from unittest.mock import patch

import pytest

from app.core import sentry as sentry_module


@pytest.fixture(autouse=True)
def reset_sentry_module():
    """Each test starts with ``_initialized = False``."""
    sentry_module._reset_for_tests()
    yield
    sentry_module._reset_for_tests()


def test_init_noop_without_dsn(monkeypatch):
    """No DSN → no init, no exception, returns False."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert sentry_module.init_sentry(dsn="") is False
    assert sentry_module.is_initialized() is False


def test_init_noop_when_env_dsn_blank(monkeypatch):
    """Empty-string DSN from env counts as unset."""
    monkeypatch.setenv("SENTRY_DSN", "   ")  # whitespace-only
    assert sentry_module.init_sentry() is False
    assert sentry_module.is_initialized() is False


def test_init_returns_true_with_dsn():
    """A syntactically-valid DSN initialises Sentry — but we don't want
    the test hitting sentry.io, so we patch the real init call."""
    with patch("sentry_sdk.init") as mock_init:
        result = sentry_module.init_sentry(
            dsn="https://abc@o0.ingest.sentry.io/1",
            environment="test",
            release="pytest",
            traces_sample_rate=0.0,
        )
    assert result is True
    assert sentry_module.is_initialized() is True
    mock_init.assert_called_once()
    # Verify the important flags actually got passed through.
    kwargs = mock_init.call_args.kwargs
    assert kwargs["dsn"] == "https://abc@o0.ingest.sentry.io/1"
    assert kwargs["environment"] == "test"
    assert kwargs["send_default_pii"] is False
    assert kwargs["traces_sample_rate"] == 0.0


def test_init_is_idempotent():
    """Calling ``init_sentry`` twice is a no-op on the second call."""
    with patch("sentry_sdk.init") as mock_init:
        assert sentry_module.init_sentry(dsn="https://abc@o0.ingest.sentry.io/1") is True
        assert sentry_module.init_sentry(dsn="https://abc@o0.ingest.sentry.io/1") is False
    # Underlying SDK init should only run once regardless.
    assert mock_init.call_count == 1


def test_scrub_redacts_sensitive_headers():
    event = {
        "request": {
            "url": "https://example.com/api/nodes/register?api_key=secret123",
            "query_string": "api_key=secret123&other=ok",
            "headers": {
                "Authorization": "Bearer sk_live_something",
                "X-Node-API-Key": "osn_abc123",
                "Cookie": "session=xyz",
                "User-Agent": "pytest",
            },
        },
    }
    cleaned = sentry_module._scrub_event(event, hint={})
    assert cleaned is not None

    # Query string and URL query both stripped.
    assert cleaned["request"]["query_string"] == ""
    assert "?" not in cleaned["request"]["url"]
    assert "secret123" not in cleaned["request"]["url"]

    headers = cleaned["request"]["headers"]
    assert headers["Authorization"] == "[redacted]"
    assert headers["X-Node-API-Key"] == "[redacted]"
    assert headers["Cookie"] == "[redacted]"
    # Non-sensitive headers pass through.
    assert headers["User-Agent"] == "pytest"


def test_scrub_handles_events_without_request():
    """Events raised outside an HTTP context (background tasks, CLI) have
    no ``request`` — scrubbing must not crash."""
    event = {"message": "something blew up"}
    cleaned = sentry_module._scrub_event(event, hint={})
    assert cleaned == {"message": "something blew up"}


def test_helpers_noop_when_sentry_uninitialised():
    """``capture_exception`` / ``set_user_context`` must be safe to call
    before init — we sprinkle them in production code that also runs in
    tests, and failing to init Sentry should never cascade."""
    # Not initialised — both should silently return.
    sentry_module.capture_exception(ValueError("test"))
    sentry_module.set_user_context(user_id="u_1", org_id="org_1", plan="pro")
    # No assertion; the point is that nothing raised.
