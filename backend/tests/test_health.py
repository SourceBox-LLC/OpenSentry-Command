"""Basic health and security header tests."""


def test_health_endpoint(unauthenticated_client):
    """Health check should always return 200."""
    resp = unauthenticated_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_security_headers(unauthenticated_client):
    """All responses should include security headers."""
    resp = unauthenticated_client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")


# ── /api/health/detailed ─────────────────────────────────────────────


def test_health_detailed_returns_full_shape(unauthenticated_client):
    """Status-page consumers depend on the top-level keys; pin them so a
    refactor that drops one (e.g. removing `uptime_seconds` to "simplify")
    breaks the test, not silently the status page."""
    resp = unauthenticated_client.get("/api/health/detailed")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert data["version"] == "2.1.0"
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0
    assert "started_at" in data
    assert "time" in data
    assert set(data["checks"].keys()) == {
        "database", "disk", "hls_cache", "viewer_usage", "sse", "resend",
    }


def test_health_detailed_resend_check_disabled_by_default(unauthenticated_client, monkeypatch):
    """When EMAIL_ENABLED=false (the default for local dev / tests), the
    resend check reports 'disabled' rather than 'unconfigured' or 'ok'.
    This split lets the operator distinguish "I forgot to set the
    secret" from "I left the kill-switch off intentionally."
    """
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "EMAIL_ENABLED", False)

    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    assert data["checks"]["resend"]["status"] == "disabled"
    # Queue depth is always reported as an int, never None — status-page
    # consumers should be able to render it without null-checks.
    assert isinstance(data["checks"]["resend"]["queue_depth"], int)


def test_health_detailed_resend_check_unconfigured(unauthenticated_client, monkeypatch):
    """Kill-switch on but secret missing → 'unconfigured' (operator
    forgot a step).  Different from 'disabled' so the diagnosis is
    obvious from the status page."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(app_settings, "RESEND_API_KEY", "")

    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    assert data["checks"]["resend"]["status"] == "unconfigured"


def test_health_detailed_resend_check_ok_when_configured(unauthenticated_client, monkeypatch):
    """Kill-switch on AND secret set → 'ok'."""
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(app_settings, "RESEND_API_KEY", "re_test_dummy")
    monkeypatch.setattr(app_settings, "EMAIL_FROM_ADDRESS", "n@s.test")

    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    assert data["checks"]["resend"]["status"] == "ok"


def test_health_detailed_resend_queue_depth_counts_pending(unauthenticated_client, db):
    """Queue depth is the count of EmailOutbox rows in 'pending' status —
    drives status-page graphs and informs alerting on a backlog that
    isn't draining."""
    from app.models.models import EmailOutbox

    # Mix of statuses: only 'pending' should count.
    for status, n in [("pending", 3), ("sent", 5), ("failed", 1)]:
        for i in range(n):
            db.add(EmailOutbox(
                org_id="org_x",
                recipient_email=f"u{i}@x.test",
                subject="x",
                body_text="t",
                body_html="<p>t</p>",
                kind="camera_offline",
                status=status,
            ))
    db.commit()

    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    assert data["checks"]["resend"]["queue_depth"] == 3


def test_health_detailed_disk_check_returns_usage(unauthenticated_client):
    """External uptime monitors (UptimeRobot, BetterStack) poll this
    endpoint and parse `checks.disk.percent_used` to alert before the
    Fly volume fills.  Pin the shape — accidentally renaming a field
    or dropping a metric would silently break those alerts."""
    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    disk = data["checks"]["disk"]
    # In tests we don't have /data, so the fallback to '.' kicks in.
    # `error` is acceptable on platforms where shutil.disk_usage('.')
    # somehow fails; the rest of the keys must be present in the
    # success path.
    assert disk["status"] in ("ok", "warn", "critical", "error")
    assert "path" in disk
    if disk["status"] != "error":
        assert isinstance(disk["bytes_used"], int)
        assert isinstance(disk["bytes_free"], int)
        assert isinstance(disk["bytes_total"], int)
        assert isinstance(disk["percent_used"], (int, float))
        assert 0 <= disk["percent_used"] <= 100


def test_health_detailed_database_check_includes_latency(unauthenticated_client):
    """The DB latency number is the bit on-call cares about — confirm it's
    actually populated when the ping succeeds (in tests we use in-memory
    SQLite, so this should always be a small positive number)."""
    resp = unauthenticated_client.get("/api/health/detailed")
    data = resp.json()

    db = data["checks"]["database"]
    assert db["status"] == "ok"
    assert "latency_ms" in db
    assert db["latency_ms"] >= 0
    # Wide upper bound — in CI this might be a millisecond or two,
    # locally it's microseconds. Just sanity-check it's not e.g. 60_000ms.
    assert db["latency_ms"] < 5000


def test_health_detailed_does_not_leak_org_or_camera_ids(
    unauthenticated_client, db,
):
    """Privacy regression: the endpoint is unauthenticated so it must
    NOT include identifiers (org_id, camera_id, user_id, email) in any
    field. Counts are fine; identifiers are not."""
    # Seed something so the cache + subscriber maps could leak names if
    # we built them wrong.
    from app.api.hls import _playlist_cache, _segment_cache
    from app.api.notifications import notification_broadcaster
    import asyncio as _asyncio

    _playlist_cache["org_secret_camera_123"] = ("playlist body", 0.0)
    _segment_cache["org_secret_camera_123"] = {}
    notification_broadcaster._subscribers["org_secret_456"] = [
        (_asyncio.Queue(), False),
    ]
    try:
        resp = unauthenticated_client.get("/api/health/detailed")
        body = resp.text  # raw text — searches into all values
        assert "org_secret_camera_123" not in body
        assert "org_secret_456" not in body

        # Counts must still reflect the seeded data, otherwise we'd be
        # passing this assertion by accidentally returning empty.
        data = resp.json()
        assert data["checks"]["hls_cache"]["playlists_cached"] >= 1
        assert data["checks"]["sse"]["subscriber_orgs"] >= 1
    finally:
        # Cleanup so the seeded entries don't leak into the next test.
        _playlist_cache.pop("org_secret_camera_123", None)
        _segment_cache.pop("org_secret_camera_123", None)
        notification_broadcaster._subscribers.pop("org_secret_456", None)


def test_health_detailed_status_unhealthy_when_db_down(
    unauthenticated_client, monkeypatch,
):
    """If the DB ping raises, overall status flips to "unhealthy" and the
    error class surfaces (but not the exception message — that could
    contain connection strings)."""
    from app import main

    class _FakeSession:
        def execute(self, *_a, **_kw):
            raise RuntimeError("boom — would-be-leaked DSN here")

        def close(self):
            pass

    monkeypatch.setattr(main, "SessionLocal", lambda: _FakeSession())

    resp = unauthenticated_client.get("/api/health/detailed")
    assert resp.status_code == 200  # endpoint itself still works
    data = resp.json()

    assert data["status"] == "unhealthy"
    assert data["checks"]["database"]["status"] == "error"
    assert data["checks"]["database"]["error_class"] == "RuntimeError"
    # Crucially, the exception message must NOT have leaked.
    assert "would-be-leaked" not in resp.text
    assert "DSN" not in resp.text
