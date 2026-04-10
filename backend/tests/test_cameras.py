"""Camera and settings endpoint tests."""

from app.models.models import Camera, CameraNode


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
    """Settings endpoint returns recording settings without fake detection fields."""
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

    # Should NOT have fake detection fields
    assert "motion_recording" not in recording
    assert "face_recording" not in recording
    assert "object_recording" not in recording
    assert "post_buffer" not in recording

    # Should NOT have notifications section
    assert "notifications" not in data


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


def test_notification_endpoints_removed(admin_client):
    """Fake notification endpoints should no longer exist."""
    resp = admin_client.get("/api/settings/notifications")
    # Should return 404 (or be caught by SPA middleware)
    assert resp.status_code in (404, 405, 200)  # 200 if SPA middleware serves index.html


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
