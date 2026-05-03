"""
Tests for the disk-critical alert loop (app.main._check_and_emit_disk_critical).

The loop itself is just a sleep + call wrapper.  The interesting
behaviour lives in the function — threshold check, debounce, per-org
fan-out — so the tests drive that function directly with a fake
``shutil.disk_usage`` stub.

Why this matters:
  - 95%-full disk → recordings/audit-logs start failing silently
  - The alert needs to fire BEFORE writes break, not after
  - But it also can't spam the same alert every 5 minutes for 6 hours
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest

import app.main as main_mod
from app.models.models import CameraNode, Notification


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


def _seed_org_with_node(db, org_id="org_test123"):
    """Disk-critical only emits to orgs that have at least one node.
    A test that wants the emit to fire must set up that condition."""
    db.add(CameraNode(
        node_id="node_for_disk_test",
        org_id=org_id,
        name="disk-check node",
        api_key_hash="x" * 64,
    ))
    db.commit()


# ── Threshold behaviour ─────────────────────────────────────────────

def test_under_threshold_no_emit(db, monkeypatch):
    """50% full → no notification, no debounce set."""
    _seed_org_with_node(db)
    _stub_disk_usage(monkeypatch, used_pct=50.0)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert db.query(Notification).count() == 0
    assert main_mod._disk_critical_last_emit_monotonic is None


def test_just_under_threshold_no_emit(db, monkeypatch):
    """94.9% — close to but below threshold.  Pin the boundary so
    a future tweak to the threshold value is visible in test diff."""
    _seed_org_with_node(db)
    _stub_disk_usage(monkeypatch, used_pct=94.9)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert db.query(Notification).count() == 0


def test_over_threshold_emits_notification(db, monkeypatch):
    """96% — over threshold → one notification per org."""
    _seed_org_with_node(db)
    _stub_disk_usage(monkeypatch, used_pct=96.0)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is True
    notifs = db.query(Notification).all()
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "disk_critical"
    assert n.audience == "admin"
    assert n.severity == "critical"
    assert "96.0%" in n.body  # rendered into the body for operator visibility


def test_over_threshold_emits_to_every_org_with_node(db, monkeypatch):
    """The disk belongs to the Command Center, not to a single org —
    every org with skin in the game (i.e. at least one node) must
    get the alert."""
    for org in ("org_a", "org_b", "org_c"):
        db.add(CameraNode(
            node_id=f"node_{org}",
            org_id=org,
            name=org,
            api_key_hash="x" * 64,
        ))
    db.commit()
    _stub_disk_usage(monkeypatch, used_pct=99.0)

    main_mod._check_and_emit_disk_critical(db)

    notifs = db.query(Notification).all()
    org_ids = {n.org_id for n in notifs}
    assert org_ids == {"org_a", "org_b", "org_c"}


def test_no_orgs_with_nodes_does_not_set_debounce(db, monkeypatch):
    """Brand-new install with zero nodes → no orgs to notify, no
    notifications, AND no debounce set so the FIRST org to register
    a node still triggers an alert immediately."""
    _stub_disk_usage(monkeypatch, used_pct=99.0)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert main_mod._disk_critical_last_emit_monotonic is None


# ── Debounce behaviour ─────────────────────────────────────────────

def test_emit_then_immediate_recheck_does_not_double_emit(db, monkeypatch):
    """Two ticks back-to-back at 99% → only one notification.  The
    debounce window is 6h by default; consecutive 5-min ticks must
    fall inside it."""
    _seed_org_with_node(db)
    _stub_disk_usage(monkeypatch, used_pct=99.0)

    main_mod._check_and_emit_disk_critical(db)
    main_mod._check_and_emit_disk_critical(db)

    assert db.query(Notification).count() == 1


def test_recovery_below_threshold_clears_debounce(db, monkeypatch):
    """Disk goes 99% → 50% → 99% — the recovery in between resets
    the debounce so the second crisis emits immediately rather than
    waiting out a stale 6h cooldown from the first one."""
    _seed_org_with_node(db)

    _stub_disk_usage(monkeypatch, used_pct=99.0)
    main_mod._check_and_emit_disk_critical(db)
    assert db.query(Notification).count() == 1

    _stub_disk_usage(monkeypatch, used_pct=50.0)
    main_mod._check_and_emit_disk_critical(db)  # clears debounce

    _stub_disk_usage(monkeypatch, used_pct=99.0)
    main_mod._check_and_emit_disk_critical(db)
    assert db.query(Notification).count() == 2


def test_disk_usage_stat_failure_returns_false(db, monkeypatch):
    """``shutil.disk_usage`` raising (e.g. /data unmounted) must NOT
    crash the loop or emit anything — just returns False and logs.
    The next tick will retry."""
    _seed_org_with_node(db)

    def boom(path):
        raise OSError("filesystem error")
    monkeypatch.setattr(main_mod.shutil, "disk_usage", boom)

    emitted = main_mod._check_and_emit_disk_critical(db)

    assert emitted is False
    assert db.query(Notification).count() == 0


def test_emit_includes_useful_metadata(db, monkeypatch):
    """The notification's `meta` field carries the actual percent and
    bytes-free values — useful for the dashboard to render rich UI
    around the alert without re-querying the OS."""
    _seed_org_with_node(db)
    _stub_disk_usage(monkeypatch, used_pct=97.5)

    main_mod._check_and_emit_disk_critical(db)

    notif = db.query(Notification).first()
    import json as _json
    meta = _json.loads(notif.meta_json)
    assert meta["percent_used"] == 97.5
    assert isinstance(meta["bytes_free"], int)
    assert meta["bytes_free"] > 0
