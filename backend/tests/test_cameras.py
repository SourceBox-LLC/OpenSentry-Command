"""Camera and settings endpoint tests."""

from app.models.models import Setting



def test_list_cameras_empty(admin_client):
    """Empty org returns empty camera list."""
    from app.core.auth import require_view
    from tests.conftest import _make_admin_user
    app = admin_client.app
    app.dependency_overrides[require_view] = lambda: _make_admin_user()

    resp = admin_client.get("/api/cameras")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_settings(admin_client):
    """Settings endpoint returns recording + notification sections."""
    from app.core.auth import require_view
    from tests.conftest import _make_admin_user
    app = admin_client.app
    app.dependency_overrides[require_view] = lambda: _make_admin_user()

    resp = admin_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()

    # Should have recording settings
    assert "recording" in data
    recording = data["recording"]
    assert "scheduled_recording" in recording
    assert "continuous_24_7" in recording

    # Should NOT have fake detection fields — these were removed because
    # the backend never actually did motion/face/object recording.
    assert "motion_recording" not in recording
    assert "face_recording" not in recording
    assert "object_recording" not in recording
    assert "post_buffer" not in recording

    # Should have notifications section with all three toggles defaulted on
    # (backwards compat: orgs that pre-date the toggle default to everything
    # enabled, same behaviour they had before).
    assert "notifications" in data
    notifications = data["notifications"]
    assert notifications["motion_notifications"] is True
    assert notifications["camera_transition_notifications"] is True
    assert notifications["node_transition_notifications"] is True


def test_update_recording_settings(admin_client):
    """Can update recording settings."""
    resp = admin_client.post("/api/settings/recording", json={
        "scheduled_recording": True,
        "scheduled_start": "08:00",
        "scheduled_end": "18:00",
        "continuous_24_7": False,
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_get_notification_settings_defaults_on(admin_client):
    """New orgs see all notification toggles enabled by default."""
    resp = admin_client.get("/api/settings/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["motion_notifications"] is True
    assert body["camera_transition_notifications"] is True
    assert body["node_transition_notifications"] is True


def test_update_notification_settings(admin_client):
    """Admin can flip motion notifications off and the change persists."""
    resp = admin_client.post("/api/settings/notifications", json={
        "motion_notifications": False,
        "camera_transition_notifications": True,
        "node_transition_notifications": True,
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Round-trip: GET must reflect the change
    follow = admin_client.get("/api/settings/notifications")
    assert follow.status_code == 200
    body = follow.json()
    assert body["motion_notifications"] is False
    assert body["camera_transition_notifications"] is True
    assert body["node_transition_notifications"] is True


def test_notification_settings_reflected_in_all_settings(admin_client):
    """After toggling motion off, /api/settings aggregate shows the change."""
    admin_client.post("/api/settings/notifications", json={
        "motion_notifications": False,
        "camera_transition_notifications": True,
        "node_transition_notifications": True,
    })
    resp = admin_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["notifications"]["motion_notifications"] is False


def test_update_notification_settings_requires_admin(viewer_client):
    """Non-admin members can't flip the toggles."""
    resp = viewer_client.post("/api/settings/notifications", json={
        "motion_notifications": False,
        "camera_transition_notifications": True,
        "node_transition_notifications": True,
    })
    # require_admin yields 401/403/404 depending on the auth layer's
    # rejection path — viewer_client doesn't override require_admin so
    # the real dependency runs and rejects.
    assert resp.status_code in (401, 403)


# ─── Danger zone (wipe-logs, full-reset) ─────────────────────────────
#
# These two endpoints are destructive and gated on a paid plan.  The
# audit flagged that the gate read ONLY the JWT `features` claim,
# which has up to ~1 minute of refresh lag after a Clerk plan change.
# A user who downgrades from Pro → Free would still pass the JWT
# check during that window and could fire the destructive action
# despite no longer having entitlement.  v0.1.40+ adds a server-side
# double-check via effective_plan_for_caps (DB-resolved current
# plan).  These tests pin both sides of the gate.


def _force_org_plan(monkeypatch, plan_slug: str) -> None:
    """Override the DB-resolved plan that the danger-zone helper sees.

    Patches ``effective_plan_for_caps`` at its definition site so the
    test doesn't need a Clerk SDK or a populated webhook cache.
    """
    from app.core import plans as plans_mod
    monkeypatch.setattr(
        plans_mod, "effective_plan_for_caps", lambda _db, _org: plan_slug
    )


def test_wipe_logs_requires_paid_plan_in_db_not_just_jwt(
    admin_client, monkeypatch
):
    """admin_client's JWT has features=['admin'], so the JWT gate
    passes.  But if the DB-resolved plan is free_org (e.g. user just
    downgraded but the JWT hasn't refreshed), the second check
    rejects with 403.  Stops the post-downgrade exploit window."""
    _force_org_plan(monkeypatch, "free_org")

    resp = admin_client.post("/api/settings/danger/wipe-logs")
    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


def test_wipe_logs_succeeds_when_db_plan_is_paid(admin_client, monkeypatch):
    """Both gates pass: JWT has admin, DB says pro.  Wipe goes through."""
    _force_org_plan(monkeypatch, "pro")

    resp = admin_client.post("/api/settings/danger/wipe-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "deleted_logs" in body


def test_full_reset_requires_paid_plan_in_db_not_just_jwt(
    admin_client, monkeypatch
):
    """Same exploit window as wipe-logs but for full_reset, which is
    the more destructive of the two — wipes nodes, cameras, settings,
    audit log."""
    _force_org_plan(monkeypatch, "free_org")

    resp = admin_client.post("/api/settings/danger/full-reset")
    assert resp.status_code == 403
    assert "paid" in resp.json()["detail"].lower()


def test_full_reset_succeeds_when_db_plan_is_paid(admin_client, monkeypatch):
    _force_org_plan(monkeypatch, "pro_plus")

    resp = admin_client.post("/api/settings/danger/full-reset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "nodes_deleted" in body


def test_camera_groups_crud(admin_client):
    """Create, list, and delete camera groups."""
    from app.core.auth import require_view
    from tests.conftest import _make_admin_user
    app = admin_client.app
    app.dependency_overrides[require_view] = lambda: _make_admin_user()

    # Create
    resp = admin_client.post("/api/camera-groups", json={"name": "Front Yard"})
    assert resp.status_code == 200
    group_id = resp.json()["id"]

    # List
    resp = admin_client.get("/api/camera-groups")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Front Yard"

    # Delete
    resp = admin_client.delete(f"/api/camera-groups/{group_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = admin_client.get("/api/camera-groups")
    assert len(resp.json()) == 0

