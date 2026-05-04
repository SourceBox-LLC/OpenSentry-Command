"""
Tests for the disk-critical alert loop (app.main._check_and_emit_disk_critical).

Behaviour as of 2026-05-04: disk-critical is an OPERATOR signal, not
a customer notification.  When the volume crosses 95%, the function
emits via ``logger.error()`` with structured fields (Sentry captures
this when SENTRY_DSN is set).  No Notification rows, no EmailOutbox
rows, nothing fans out to org admins — they can't ``fly volumes
extend`` our infrastructure and shouldn't be paged about it.

The tests pin three things:
  - The threshold check (95% boundary)
  - The 6h debounce (don't spam Sentry)
  - The structured ``extra`` payload on the log call (so a Sentry
    dashboard / alert rule can route on the fields)

What we explicitly DO NOT test:
  - Per-org fan-out (was removed, see project_notification_channels memory)
  - Notification table writes (same)
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import app.main as main_mod
from app.models.models import Notification


@pytest.fixture(autouse=True)
def _reset_debounce():
    """Per-process debounce is module-level state — clear between
    tests so emit-or-not is deterministic."""
    main_mod._disk_critical_last_emit_monotonic = None
    yield
    main_mod._disk_critical_last_emit_monotonic = None


def _stub_disk_usage(monkeypatch, *, used_pct: float):
    """Make ``shutil.disk_usage`` report a given percent-full.

    We don't care about the real numbers — just the ratio.  Patches
    the symbol in main_mod (which imported shutil at module level)
    rather than shutil itself, so other code that uses shutil isn't
    affected during the test."""
    total = 1_000_000_000
    used = int(total * used_pct / 100.0)
    free = total - used
    fake = SimpleNamespace(total=total, used=used, free=free)

    monkeypatch.setattr(main_mod.shutil, "disk_usage", lambda path: fake)


# ── Threshold behaviour ─────────────────────────────────────────────

def test_under_threshold_no_emit(db, monkeypatch, caplog):
    """50% full → no log emit, no debounce set."""
    _stub_disk_usage(monkeypatch, used_pct=50.0)

    with caplog.at_level(logging.ERROR, logger=main_mod.logger.name):
        emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert main_mod._disk_critical_last_emit_monotonic is None
    assert not any("OPERATOR ALERT" in r.message for r in caplog.records)


def test_just_under_threshold_no_emit(db, monkeypatch, caplog):
    """94.9% — close to but below threshold.  Pin the boundary so
    a future tweak to the threshold value is visible in test diff."""
    _stub_disk_usage(monkeypatch, used_pct=94.9)

    with caplog.at_level(logging.ERROR, logger=main_mod.logger.name):
        emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert not any("OPERATOR ALERT" in r.message for r in caplog.records)


def test_over_threshold_emits_operator_alert(db, monkeypatch, caplog):
    """96% → one structured logger.error call.  Sentry's logging
    integration captures these as events in production."""
    _stub_disk_usage(monkeypatch, used_pct=96.0)

    with caplog.at_level(logging.ERROR, logger=main_mod.logger.name):
        emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is True
    alert_records = [r for r in caplog.records if "OPERATOR ALERT" in r.message]
    assert len(alert_records) == 1
    rec = alert_records[0]
    assert rec.levelname == "ERROR"
    # Structured fields the Sentry dashboard / alert rules can route on.
    assert rec.disk_percent_used == 96.0
    assert rec.disk_bytes_free > 0
    assert rec.disk_path in ("/data", ".")
    assert rec.alert_audience == "operator_only"


def test_over_threshold_does_NOT_create_customer_notifications(db, monkeypatch):
    """Regression test for the multi-tenant violation removed
    2026-05-04: even at 99% disk, ZERO Notification rows must be
    created.  The disk is platform infrastructure; customer org
    admins cannot act on it and shouldn't be paged about it."""
    _stub_disk_usage(monkeypatch, used_pct=99.0)

    main_mod._check_and_emit_disk_critical(db)

    assert db.query(Notification).count() == 0


def test_disk_usage_stat_failure_returns_false(db, monkeypatch, caplog):
    """``shutil.disk_usage`` raising (e.g. /data unmounted) must NOT
    crash the loop or emit anything — just returns False and logs
    a warning.  The next tick will retry."""

    def boom(path):
        raise OSError("filesystem error")
    monkeypatch.setattr(main_mod.shutil, "disk_usage", boom)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    # No OPERATOR ALERT log line either — we don't know what the
    # state is so we don't claim anything.
    assert not any("OPERATOR ALERT" in r.message for r in caplog.records)


# ── Debounce behaviour ─────────────────────────────────────────────

def test_emit_then_immediate_recheck_does_not_double_emit(db, monkeypatch, caplog):
    """Two ticks back-to-back at 99% → only one OPERATOR ALERT log
    call.  Debounce window is 6h by default; consecutive 5-min ticks
    must fall inside it (Sentry quotas, alert fatigue)."""
    _stub_disk_usage(monkeypatch, used_pct=99.0)

    with caplog.at_level(logging.ERROR, logger=main_mod.logger.name):
        main_mod._check_and_emit_disk_critical(db)
        main_mod._check_and_emit_disk_critical(db)

    alert_records = [r for r in caplog.records if "OPERATOR ALERT" in r.message]
    assert len(alert_records) == 1


def test_recovery_below_threshold_clears_debounce(db, monkeypatch, caplog):
    """Disk goes 99% → 50% → 99% — the recovery in between resets
    the debounce so the second crisis emits immediately rather than
    waiting out a stale 6h cooldown from the first one."""

    with caplog.at_level(logging.ERROR, logger=main_mod.logger.name):
        _stub_disk_usage(monkeypatch, used_pct=99.0)
        main_mod._check_and_emit_disk_critical(db)

        _stub_disk_usage(monkeypatch, used_pct=50.0)
        main_mod._check_and_emit_disk_critical(db)  # clears debounce

        _stub_disk_usage(monkeypatch, used_pct=99.0)
        main_mod._check_and_emit_disk_critical(db)

    alert_records = [r for r in caplog.records if "OPERATOR ALERT" in r.message]
    assert len(alert_records) == 2


# ── /api/health/detailed integration (operator-monitoring path) ────

def test_health_detailed_surfaces_disk_usage(unauthenticated_client):
    """The operator-monitoring contract: ``/api/health/detailed``
    must always include a ``disk`` block with ``percent_used`` and
    ``status`` fields.  External monitors (UptimeRobot, BetterStack,
    status pages) poll this endpoint to detect disk-full BEFORE
    SQLite writes start failing.

    Now that we removed customer-facing disk_critical notifications,
    this endpoint IS the contract — pin its shape so a future refactor
    that "cleans up" the disk block silently breaks operator
    monitoring.  The endpoint is intentionally unauthenticated (it's
    a health endpoint pollable by external monitors)."""
    resp = unauthenticated_client.get("/api/health/detailed")
    assert resp.status_code == 200

    data = resp.json()
    # The disk block lives under `checks.disk` alongside the other
    # health checks — same shape as `checks.database`.  Pinning the
    # path explicitly guards against either layer being moved.
    assert "checks" in data
    assert "disk" in data["checks"], (
        "checks.disk is the operator-monitoring contract"
    )
    disk = data["checks"]["disk"]
    # status field is what a monitor pattern-matches on.
    assert disk.get("status") in ("ok", "warn", "critical", "error")
    # percent_used is the numeric the dashboard graphs.
    if disk["status"] != "error":
        assert "percent_used" in disk
        assert "bytes_free" in disk
        assert "bytes_total" in disk
        assert isinstance(disk["percent_used"], (int, float))
