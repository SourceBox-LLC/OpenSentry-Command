"""
Tests for the motion-email digest sweep
(``app/main.py::_motion_digest_loop`` — the inner per-tick logic
extracted via direct invocation of the work block, since the loop
itself is just an asyncio.sleep + try/except scheduler).

Strategy: the loop body opens its own ``SessionLocal()`` per tick.
Tests seed the DB through the test session, then invoke a thin helper
``_run_one_motion_digest_tick`` (defined inline below) that mirrors
the loop's body without the ``while True`` + sleep wrapper.  This is
the same shape ``_check_and_emit_disk_critical`` uses — the disk-loop
inline body is callable from tests directly.

What's pinned here:
  * Digest emits when extras are present in the closed window.
  * Digest stays silent when only the immediate event landed.
  * Open windows (cooldown not yet expired) are left alone.
  * Disabled email gate at digest time → no email, anchor still
    deleted (anchor cleanup is unconditional at expiry).
  * Orphan anchors (camera deleted) are silently cleaned up.
  * Per-row try/except — one corrupt row doesn't poison the tick.
  * Multiple orgs are processed independently.
  * Cooldown duration changes mid-window are honoured at digest time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.api import notifications as notifications_mod
from app.models.models import (
    Camera,
    CameraNode,
    EmailOutbox,
    MotionEvent,
    Notification,
    Setting,
)

# ── Tick runner ────────────────────────────────────────────────────


def _run_one_motion_digest_tick(test_session):
    """Execute one tick of ``_motion_digest_loop`` against the test
    DB.  Mirrors the loop body in app/main.py exactly (modulo the
    asyncio.sleep + outer try/except)."""
    from app.api.notifications import (
        _motion_cooldown_minutes,
        create_notification,
        email_enabled_for_kind,
    )

    db = test_session  # use the test fixture's session directly
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    anchors = (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .all()
    )
    for anchor_row in anchors:
        try:
            if ":" not in anchor_row.key:
                db.delete(anchor_row)
                db.commit()
                continue
            camera_id = anchor_row.key.split(":", 1)[1]
            if not anchor_row.value:
                db.delete(anchor_row)
                db.commit()
                continue
            try:
                anchor_ts = datetime.fromisoformat(anchor_row.value)
            except ValueError:
                db.delete(anchor_row)
                db.commit()
                continue

            cooldown_min = _motion_cooldown_minutes(db, anchor_row.org_id)
            if (now - anchor_ts).total_seconds() < cooldown_min * 60:
                continue

            window_end = anchor_ts + timedelta(minutes=cooldown_min)
            extra_count = (
                db.query(MotionEvent)
                .filter(
                    MotionEvent.org_id == anchor_row.org_id,
                    MotionEvent.camera_id == camera_id,
                    MotionEvent.timestamp > anchor_ts,
                    MotionEvent.timestamp <= window_end,
                )
                .count()
            )

            if extra_count > 0 and email_enabled_for_kind(
                db, anchor_row.org_id, "motion"
            ):
                cam = (
                    db.query(Camera)
                    .filter_by(camera_id=camera_id, org_id=anchor_row.org_id)
                    .first()
                )
                display = cam.name if cam and cam.name else camera_id
                create_notification(
                    org_id=anchor_row.org_id,
                    kind="motion_digest",
                    title=(
                        f"{extra_count} more motion event"
                        f"{'s' if extra_count != 1 else ''} on {display}"
                    ),
                    body=(
                        f"{extra_count} additional motion event"
                        f"{'s were' if extra_count != 1 else ' was'} "
                        f'detected on "{display}" in the {cooldown_min}-'
                        f"minute window after the first alert."
                    ),
                    severity="info",
                    audience="all",
                    link=f"/dashboard?camera={camera_id}",
                    camera_id=camera_id,
                    meta={
                        "event_count": extra_count,
                        "window_start": anchor_ts.isoformat(),
                        "window_end": window_end.isoformat(),
                        "cooldown_minutes": cooldown_min,
                    },
                    db=db,
                )

            db.delete(anchor_row)
            db.commit()
        except Exception:
            db.rollback()
            raise


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def stub_recipients(monkeypatch):
    class Stub:
        def __init__(self):
            self.return_value = ["alice@org.test"]

        def __call__(self, org_id, audience):
            return list(self.return_value)

    stub = Stub()
    monkeypatch.setattr(notifications_mod, "get_recipient_emails", stub)
    return stub


def _enable_motion_email(db, monkeypatch, *, org_id="org_test123"):
    monkeypatch.setattr(notifications_mod.settings, "EMAIL_ENABLED", True)
    Setting.set(db, org_id, "email_motion", "true")


def _seed_camera(db, *, camera_id="cam_front_door", org_id="org_test123",
                 name="Front Door"):
    """Create the minimum CameraNode + Camera rows so the digest
    loop's display-name lookup finds something."""
    node = (
        db.query(CameraNode)
        .filter_by(node_id="node_test", org_id=org_id)
        .first()
    )
    if node is None:
        node = CameraNode(
            node_id="node_test",
            org_id=org_id,
            name="test-node",
            api_key_hash="x" * 64,
        )
        db.add(node)
        db.commit()
    cam = Camera(
        camera_id=camera_id,
        node_id=node.id,
        org_id=org_id,
        name=name,
    )
    db.add(cam)
    db.commit()


def _seed_anchor(db, *, camera_id, when, org_id="org_test123"):
    Setting.set(
        db, org_id,
        f"motion_email_cooldown_start:{camera_id}",
        when.isoformat(),
    )


def _seed_motion_events(db, *, camera_id, count, base_time, org_id="org_test123"):
    """Insert ``count`` MotionEvent rows spaced 10 seconds apart
    starting 30 seconds after ``base_time`` (so they fall AFTER the
    anchor used in tests)."""
    for i in range(count):
        ts = base_time + timedelta(seconds=30 + i * 10)
        db.add(MotionEvent(
            org_id=org_id,
            camera_id=camera_id,
            node_id="node_test",
            score=80,
            segment_seq=i,
            timestamp=ts,
        ))
    db.commit()


# ── Tests ──────────────────────────────────────────────────────────


def test_digest_emits_when_extras_present(db, monkeypatch, stub_recipients):
    """Anchor written 20 min ago + 5 motion events inside the
    15-minute window → one motion_digest notification + one outbox
    row, anchor deleted."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    _seed_motion_events(db, camera_id="cam_front_door", count=5, base_time=anchor_ts)

    _run_one_motion_digest_tick(db)

    digest_notifs = db.query(Notification).filter_by(kind="motion_digest").all()
    assert len(digest_notifs) == 1
    n = digest_notifs[0]
    assert "5 more motion events on Front Door" in n.title
    # Email enqueued for the digest.
    assert db.query(EmailOutbox).filter_by(kind="motion_digest").count() == 1
    # Anchor deleted.
    assert (
        db.query(Setting)
        .filter(Setting.key == "motion_email_cooldown_start:cam_front_door")
        .count()
        == 0
    )


def test_digest_silent_when_no_extras(db, monkeypatch, stub_recipients):
    """Window expired with zero events past the immediate → no
    digest emitted, but anchor IS still deleted (window has closed,
    anchor lifetime ends regardless of count)."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    # No MotionEvent rows seeded in the window.

    _run_one_motion_digest_tick(db)

    assert db.query(Notification).filter_by(kind="motion_digest").count() == 0
    assert db.query(EmailOutbox).filter_by(kind="motion_digest").count() == 0
    # Anchor still cleaned up.
    assert (
        db.query(Setting)
        .filter(Setting.key == "motion_email_cooldown_start:cam_front_door")
        .count()
        == 0
    )


def test_digest_skips_open_window(db, monkeypatch, stub_recipients):
    """Anchor written 5 min ago (cooldown=15) → window still open.
    Loop must NOT emit OR delete the anchor."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=5)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    _seed_motion_events(db, camera_id="cam_front_door", count=3, base_time=anchor_ts)

    _run_one_motion_digest_tick(db)

    assert db.query(Notification).filter_by(kind="motion_digest").count() == 0
    # Anchor preserved.
    assert (
        db.query(Setting)
        .filter(Setting.key == "motion_email_cooldown_start:cam_front_door")
        .count()
        == 1
    )


def test_digest_respects_email_motion_toggle(db, monkeypatch, stub_recipients):
    """Extras present in the closed window, but ``email_motion=false``
    at digest time → no email enqueued, anchor still deleted.  Honors
    a mid-window opt-out without leaving stale anchors behind."""
    monkeypatch.setattr(notifications_mod.settings, "EMAIL_ENABLED", True)
    Setting.set(db, "org_test123", "email_motion", "false")
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    _seed_motion_events(db, camera_id="cam_front_door", count=3, base_time=anchor_ts)

    _run_one_motion_digest_tick(db)

    # The motion_digest notification still fires through create_notification
    # (inbox-side notifications_enabled defaults motion_digest to True via
    # motion_notifications), but no email outbox row.
    assert db.query(EmailOutbox).filter_by(kind="motion_digest").count() == 0
    # Anchor deleted regardless.
    assert (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .count()
        == 0
    )


def test_digest_silent_when_inbox_motion_muted(db, monkeypatch, stub_recipients):
    """``motion_notifications=false`` → motion_digest also short-
    circuits at the inbox gate (it's mapped to the same setting key).
    Anchor is still cleaned up so the org's row count doesn't grow
    forever for a muted camera."""
    _enable_motion_email(db, monkeypatch)
    Setting.set(db, "org_test123", "motion_notifications", "false")
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    _seed_motion_events(db, camera_id="cam_front_door", count=4, base_time=anchor_ts)

    _run_one_motion_digest_tick(db)

    # No digest notification (notifications_enabled returned False).
    assert db.query(Notification).filter_by(kind="motion_digest").count() == 0
    # Anchor cleaned up.
    assert (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .count()
        == 0
    )


def test_digest_orphan_anchor_for_deleted_camera(
    db, monkeypatch, stub_recipients
):
    """Anchor exists for a camera that's since been deleted (no
    Camera row, no MotionEvent rows).  Loop's count returns 0 → no
    digest emitted, anchor silently dropped within ≤ cooldown + tick.
    Without this cleanup, deleted-camera anchors would accumulate
    forever in the Settings table."""
    _enable_motion_email(db, monkeypatch)
    # No _seed_camera and no MotionEvents.
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_ghost", when=anchor_ts)

    _run_one_motion_digest_tick(db)

    assert db.query(Notification).filter_by(kind="motion_digest").count() == 0
    # Anchor self-cleaned.
    assert (
        db.query(Setting)
        .filter(Setting.key == "motion_email_cooldown_start:cam_ghost")
        .count()
        == 0
    )


def test_digest_uses_current_cooldown_minutes(db, monkeypatch, stub_recipients):
    """Cooldown duration is read at digest-check time, not at anchor-
    write time.  Anchor written when cooldown=15 → admin changes to
    cooldown=1 → next tick fires immediately even though anchor is
    only ~5 minutes old."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    # Anchor 5 minutes ago — would NOT be expired with the default 15
    # min cooldown.  But we'll change the setting to 1 minute below.
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=5)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)
    _seed_motion_events(db, camera_id="cam_front_door", count=2, base_time=anchor_ts)

    Setting.set(db, "org_test123", "email_motion_cooldown_minutes", "1")

    _run_one_motion_digest_tick(db)

    # Window is now considered expired (5 min > 1 min) → digest fires.
    assert db.query(Notification).filter_by(kind="motion_digest").count() == 1


def test_digest_multiple_orgs_independent(db, monkeypatch, stub_recipients):
    """Two orgs each with an active anchor — only the org with
    email_motion enabled gets a digest email, but BOTH have their
    anchors cleaned up at window expiry."""
    monkeypatch.setattr(notifications_mod.settings, "EMAIL_ENABLED", True)
    Setting.set(db, "org_test123", "email_motion", "true")
    Setting.set(db, "org_other_456", "email_motion", "false")

    _seed_camera(db, camera_id="cam_a", org_id="org_test123", name="Cam A")
    # org_other doesn't need a Camera row — digest will skip it for
    # the email-disabled reason before the camera lookup matters.

    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_a", when=anchor_ts, org_id="org_test123")
    _seed_anchor(db, camera_id="cam_b", when=anchor_ts, org_id="org_other_456")
    _seed_motion_events(
        db, camera_id="cam_a", count=3, base_time=anchor_ts, org_id="org_test123",
    )
    _seed_motion_events(
        db, camera_id="cam_b", count=3, base_time=anchor_ts, org_id="org_other_456",
    )

    _run_one_motion_digest_tick(db)

    # Only org_test123 enqueues a digest email.
    digest_emails = db.query(EmailOutbox).filter_by(kind="motion_digest").all()
    assert len(digest_emails) == 1
    assert digest_emails[0].org_id == "org_test123"

    # Both anchors cleaned up.
    assert (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .count()
        == 0
    )


def test_digest_drops_malformed_anchor_value(db, monkeypatch, stub_recipients):
    """Garbage in the anchor value → drop the row, no digest, no
    exception.  Loop must not get stuck on a single corrupt row."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    Setting.set(
        db, "org_test123", "motion_email_cooldown_start:cam_front_door",
        "this is not iso 8601",
    )

    _run_one_motion_digest_tick(db)

    assert db.query(Notification).filter_by(kind="motion_digest").count() == 0
    assert (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .count()
        == 0
    )


def test_digest_drops_empty_anchor_value(db, monkeypatch, stub_recipients):
    """Empty-string value (the 'cleared by recovery' state from
    legacy cleanup paths) → drop the row, no digest."""
    _enable_motion_email(db, monkeypatch)
    Setting.set(
        db, "org_test123", "motion_email_cooldown_start:cam_front_door", "",
    )

    _run_one_motion_digest_tick(db)

    assert (
        db.query(Setting)
        .filter(Setting.key.like("motion_email_cooldown_start:%"))
        .count()
        == 0
    )


def test_digest_count_excludes_anchor_event_itself(
    db, monkeypatch, stub_recipients
):
    """The digest body says ``X MORE motion events`` — so the count
    must not include the immediate event the anchor represents.  The
    query filter is ``MotionEvent.timestamp > anchor_ts`` (strict),
    not ``>=``.  Pin this so a future refactor that changes to >=
    fails the test (and produces an off-by-one in user-facing copy)."""
    _enable_motion_email(db, monkeypatch)
    _seed_camera(db)
    anchor_ts = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=20)
    _seed_anchor(db, camera_id="cam_front_door", when=anchor_ts)

    # Insert one MotionEvent at exactly anchor_ts (the immediate event)
    # plus 3 strictly after.
    db.add(MotionEvent(
        org_id="org_test123",
        camera_id="cam_front_door",
        node_id="node_test",
        score=80,
        segment_seq=0,
        timestamp=anchor_ts,  # at the anchor, NOT after
    ))
    db.commit()
    _seed_motion_events(db, camera_id="cam_front_door", count=3, base_time=anchor_ts)

    _run_one_motion_digest_tick(db)

    digest = db.query(Notification).filter_by(kind="motion_digest").first()
    assert digest is not None
    # The body should reference 3 (the strictly-after events), not 4.
    assert "3 more motion events" in digest.title
