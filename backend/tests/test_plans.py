"""Unit tests for ``app.core.plans``."""

from datetime import datetime, timedelta, timezone

from app.core.plans import enforce_camera_cap, wire_plan_slug
from app.models.models import Camera, CameraNode, Setting
from tests.conftest import TestSession


def test_wire_plan_slug_strips_org_suffix():
    """The internal ``free_org`` slug must render as ``free`` on the wire
    so the CloudNode pill badge reads ``[ FREE ]`` rather than
    ``[ FREE_ORG ]``."""
    assert wire_plan_slug("free_org") == "free"


def test_wire_plan_slug_passes_through_clean_slugs():
    """Paid plan slugs have no suffix and must pass through untouched."""
    assert wire_plan_slug("pro") == "pro"
    assert wire_plan_slug("business") == "business"


def test_wire_plan_slug_lowercases_and_trims():
    """Defensive: upstream sources have occasionally leaked casing/whitespace
    into stored plan strings. Normalize so the node always sees canonical
    lowercase."""
    assert wire_plan_slug("  PRO  ") == "pro"
    assert wire_plan_slug("Free_Org") == "free"


def test_wire_plan_slug_passes_unknown_tiers_through():
    """A future ``enterprise`` tier must render in the node UI even before
    we ship a node update — the badge falls back to the dimmed default
    rather than being hidden."""
    assert wire_plan_slug("enterprise") == "enterprise"


def test_wire_plan_slug_handles_empty_and_none():
    """Empty inputs collapse to ``free`` so the caller never has to guard
    against ``None`` before putting the value on the wire."""
    assert wire_plan_slug("") == "free"
    assert wire_plan_slug("   ") == "free"
    # The signature is ``str`` but the helper is robust to callers that
    # forget to coalesce a missing Setting value.
    assert wire_plan_slug(None) == "free"  # type: ignore[arg-type]


# ── enforce_camera_cap ─────────────────────────────────────────────────


def _seed_org_and_cameras(db, org_id: str, count: int, plan: str | None = None) -> list[Camera]:
    """Create ``count`` Camera rows for ``org_id`` with ascending created_at.

    Older cameras get earlier timestamps so the ``ORDER BY created_at ASC``
    in `enforce_camera_cap` gives a deterministic keep/drop ordering that
    matches the real plan-downgrade path.
    """
    # A parent node is required — Camera.node_id is a FK.
    node = CameraNode(
        node_id=f"nd_{org_id[-4:]}",
        name=f"Node for {org_id}",
        org_id=org_id,
        api_key_hash="x" * 64,
        status="online",
    )
    db.add(node)
    db.flush()

    base = datetime(2024, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    cameras: list[Camera] = []
    for i in range(count):
        cam = Camera(
            camera_id=f"{org_id}_cam_{i:03d}",
            org_id=org_id,
            node_id=node.id,
            name=f"Camera {i}",
            capabilities="streaming",
            status="online",
            created_at=base + timedelta(minutes=i),
        )
        db.add(cam)
        cameras.append(cam)
    db.flush()

    if plan is not None:
        Setting.set(db, org_id, "org_plan", plan)
        db.flush()

    return cameras


def test_enforce_cap_is_noop_when_under_cap():
    """Free org with 1 camera under the 2-cap: nothing flips."""
    db = TestSession()
    try:
        _seed_org_and_cameras(db, "org_under", count=1, plan="free_org")
        result = enforce_camera_cap(db, "org_under")
        db.commit()
        assert result["changed"] is False
        assert result["disabled"] == []
        assert len(result["enabled"]) == 1

        cam = db.query(Camera).filter_by(org_id="org_under").one()
        assert cam.disabled_by_plan is False
    finally:
        db.close()


def test_enforce_cap_disables_oldest_first_on_free_plan():
    """Free org with 5 cameras over the 2-cap: the two OLDEST keep streaming;
    the other three flip to disabled. Oldest-first is deterministic and
    preserves long-lived cameras the operator cares about most."""
    db = TestSession()
    try:
        cams = _seed_org_and_cameras(db, "org_over", count=5, plan="free_org")
        result = enforce_camera_cap(db, "org_over")
        db.commit()

        assert result["changed"] is True
        assert result["max_cameras"] == 2
        assert len(result["enabled"]) == 2
        assert len(result["disabled"]) == 3

        # The 2 kept must be the 2 oldest (by created_at).
        kept = {c.camera_id for c in cams[:2]}
        assert set(result["enabled"]) == kept

        db.expire_all()
        rows = {c.camera_id: c.disabled_by_plan for c in db.query(Camera).filter_by(org_id="org_over").all()}
        assert rows[cams[0].camera_id] is False
        assert rows[cams[1].camera_id] is False
        assert all(rows[c.camera_id] is True for c in cams[2:])
    finally:
        db.close()


def test_enforce_cap_clears_flags_on_upgrade():
    """Simulate a downgrade (cameras disabled) followed by an upgrade that
    raises the cap above the current count: all disabled flags must clear."""
    db = TestSession()
    try:
        cams = _seed_org_and_cameras(db, "org_upgrade", count=5, plan="free_org")
        enforce_camera_cap(db, "org_upgrade")
        db.commit()

        disabled_before = [c for c in cams if db.get(Camera, c.id).disabled_by_plan]
        assert len(disabled_before) == 3, "free cap should have disabled 3"

        # Upgrade to Pro (10-camera cap) and re-enforce.
        Setting.set(db, "org_upgrade", "org_plan", "pro")
        db.commit()
        result = enforce_camera_cap(db, "org_upgrade")
        db.commit()

        assert result["changed"] is True
        assert result["disabled"] == []
        assert len(result["enabled"]) == 5

        db.expire_all()
        rows = db.query(Camera).filter_by(org_id="org_upgrade").all()
        assert all(r.disabled_by_plan is False for r in rows)
    finally:
        db.close()


def test_enforce_cap_is_idempotent():
    """Running the helper twice with no plan change must not flip anything
    on the second call. The webhook-and-register safety net fires on every
    heartbeat-triggered registration; it must be cheap when nothing moves."""
    db = TestSession()
    try:
        _seed_org_and_cameras(db, "org_idem", count=5, plan="free_org")
        first = enforce_camera_cap(db, "org_idem")
        db.commit()
        assert first["changed"] is True

        second = enforce_camera_cap(db, "org_idem")
        db.commit()
        assert second["changed"] is False
    finally:
        db.close()


def test_enforce_cap_treats_missing_plan_as_free():
    """Orgs that have never had a Setting row land on the free tier — the
    most restrictive default — not the most permissive."""
    db = TestSession()
    try:
        _seed_org_and_cameras(db, "org_nosetting", count=4, plan=None)
        result = enforce_camera_cap(db, "org_nosetting")
        db.commit()

        # Free cap is 2 → 2 of 4 disabled.
        assert result["changed"] is True
        assert result["max_cameras"] == 2
        assert len(result["disabled"]) == 2
    finally:
        db.close()
