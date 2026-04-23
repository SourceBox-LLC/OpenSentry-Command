"""Node management endpoint tests."""

import hashlib

from app.models.models import CameraNode
from tests.conftest import TestSession


def test_create_node(admin_client):
    """Admin can create a new node."""
    resp = admin_client.post("/api/nodes", json={"name": "Test Node"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["name"] == "Test Node"
    assert "api_key" in data
    assert "node_id" in data


def test_create_node_returns_unique_keys(admin_client):
    """Each node gets a unique API key."""
    resp1 = admin_client.post("/api/nodes", json={"name": "Node 1"})
    resp2 = admin_client.post("/api/nodes", json={"name": "Node 2"})
    assert resp1.json()["api_key"] != resp2.json()["api_key"]
    assert resp1.json()["node_id"] != resp2.json()["node_id"]


def test_list_nodes(admin_client):
    """Admin can list all nodes."""
    admin_client.post("/api/nodes", json={"name": "Node A"})
    admin_client.post("/api/nodes", json={"name": "Node B"})

    resp = admin_client.get("/api/nodes")
    assert resp.status_code == 200
    nodes = resp.json()
    assert len(nodes) == 2
    names = {n["name"] for n in nodes}
    assert names == {"Node A", "Node B"}


def test_delete_node(admin_client):
    """Admin can delete a node."""
    create_resp = admin_client.post("/api/nodes", json={"name": "Temp Node"})
    node_id = create_resp.json()["node_id"]

    delete_resp = admin_client.delete(f"/api/nodes/{node_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    # Verify it's gone
    list_resp = admin_client.get("/api/nodes")
    assert len(list_resp.json()) == 0


def test_delete_nonexistent_node(admin_client):
    """Deleting a non-existent node returns 404."""
    resp = admin_client.delete("/api/nodes/nonexistent")
    assert resp.status_code == 404


def test_decommission_self_removes_node(admin_client):
    """A node can decommission itself using its own API key — the
    server-side record is deleted, mirroring the admin DELETE path
    but authenticated by the node instead of a dashboard user."""
    create_resp = admin_client.post("/api/nodes", json={"name": "Self Decom"})
    body = create_resp.json()
    node_id = body["node_id"]
    api_key = body["api_key"]

    resp = admin_client.post(
        "/api/nodes/self/decommission",
        headers={"X-Node-API-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "deleted": node_id}

    # Node row should be gone.
    list_resp = admin_client.get("/api/nodes")
    assert len(list_resp.json()) == 0


def test_decommission_self_requires_key(admin_client):
    """Missing X-Node-API-Key → 401 (auth required, not "node not found")."""
    resp = admin_client.post("/api/nodes/self/decommission")
    assert resp.status_code == 401


def test_decommission_self_rejects_unknown_key(admin_client):
    """An API key that matches no node → 404.  Using 404 rather than 403
    because we can't distinguish "wrong key for real node" from "key
    for a node that never existed" without leaking existence info."""
    resp = admin_client.post(
        "/api/nodes/self/decommission",
        headers={"X-Node-API-Key": "definitely-not-a-real-api-key"},
    )
    assert resp.status_code == 404


def test_decommission_self_writes_audit_row(admin_client):
    """Node-initiated decommission must still leave an audit trail —
    tagged ``initiated_by: node`` so the UI can distinguish this from
    the admin-triggered DELETE /{node_id} path."""
    import json
    from app.models.models import AuditLog
    from tests.conftest import TestSession

    create_resp = admin_client.post("/api/nodes", json={"name": "Audited Decom"})
    body = create_resp.json()
    node_id = body["node_id"]
    api_key = body["api_key"]

    resp = admin_client.post(
        "/api/nodes/self/decommission",
        headers={"X-Node-API-Key": api_key},
    )
    assert resp.status_code == 200

    session = TestSession()
    try:
        rows = (
            session.query(AuditLog)
            .filter_by(event="node_decommissioned")
            .all()
        )
        assert len(rows) == 1, "expected exactly one node_decommissioned audit row"
        row = rows[0]
        assert row.username == f"node:{node_id}"
        details = json.loads(row.details)
        assert details["node_id"] == node_id
        assert details["initiated_by"] == "node"
    finally:
        session.close()


def test_get_plan_info(admin_client):
    """Plan info endpoint returns plan details and usage."""
    resp = admin_client.get("/api/nodes/plan")
    assert resp.status_code == 200
    data = resp.json()
    assert "plan" in data
    assert "limits" in data
    assert "usage" in data
    assert "payment_past_due" in data
    assert data["usage"]["nodes"] == 0
    assert data["usage"]["cameras"] == 0


def test_register_with_bad_api_key_records_error_on_node(admin_client):
    """A registration attempt with a wrong key must write
    ``last_register_error`` on the node row so the UI can surface the
    reason instead of making the user SSH into the CloudNode to read logs.
    """
    create_resp = admin_client.post("/api/nodes", json={"name": "Error Node"})
    node_id = create_resp.json()["node_id"]

    # Use an obviously-wrong API key — the real one only exists in memory.
    resp = admin_client.post(
        "/api/nodes/register",
        headers={"X-Node-API-Key": "definitely-not-the-real-key"},
        json={
            "node_id": node_id,
            "hostname": "test-host",
            "local_ip": "127.0.0.1",
            "http_port": 8765,
            "cameras": [],
        },
    )
    assert resp.status_code == 403

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node is not None
        assert node.last_register_error is not None
        assert "Invalid API key" in node.last_register_error
        assert node.last_register_error_at is not None
    finally:
        session.close()


def test_to_dict_exposes_register_error(admin_client):
    """The /api/nodes listing must surface ``last_register_error`` so the
    SettingsPage can render the warning banner without a second fetch."""
    create_resp = admin_client.post("/api/nodes", json={"name": "Failing Node"})
    node_id = create_resp.json()["node_id"]

    # Force a failure via the public endpoint rather than poking the DB,
    # so the round-trip matches what users actually hit.
    admin_client.post(
        "/api/nodes/register",
        headers={"X-Node-API-Key": "bad-key"},
        json={
            "node_id": node_id,
            "hostname": "h",
            "local_ip": "127.0.0.1",
            "http_port": 8765,
            "cameras": [],
        },
    )

    list_resp = admin_client.get("/api/nodes")
    assert list_resp.status_code == 200
    entry = next(n for n in list_resp.json() if n["node_id"] == node_id)
    assert entry["last_register_error"], entry
    assert entry["last_register_error_at"], entry


def test_register_clears_error_on_success(admin_client):
    """A successful re-registration must wipe a prior
    ``last_register_error`` so the UI stops flagging a node that's now
    fine."""
    create_resp = admin_client.post("/api/nodes", json={"name": "Recovering Node"})
    body = create_resp.json()
    node_id = body["node_id"]
    real_key = body["api_key"]

    # Bad attempt first — writes the error row.
    admin_client.post(
        "/api/nodes/register",
        headers={"X-Node-API-Key": "bad"},
        json={
            "node_id": node_id,
            "hostname": "h",
            "local_ip": "127.0.0.1",
            "http_port": 8765,
            "cameras": [],
        },
    )

    # Now a correct attempt.
    ok = admin_client.post(
        "/api/nodes/register",
        headers={"X-Node-API-Key": real_key},
        json={
            "node_id": node_id,
            "hostname": "h",
            "local_ip": "127.0.0.1",
            "http_port": 8765,
            "cameras": [],
        },
    )
    assert ok.status_code == 200

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node.last_register_error is None
        assert node.last_register_error_at is None
        assert node.api_key_hash == hashlib.sha256(real_key.encode()).hexdigest()
    finally:
        session.close()


# ── Version reporting & compatibility ────────────────────────────────


def _create_and_register(admin_client, *, version=None):
    """Helper: create a node, register it, return (node_id, api_key, response)."""
    create = admin_client.post("/api/nodes", json={"name": "Versioned Node"}).json()
    node_id, api_key = create["node_id"], create["api_key"]
    body = {
        "node_id": node_id,
        "hostname": "h",
        "local_ip": "127.0.0.1",
        "http_port": 8765,
        "cameras": [],
    }
    if version is not None:
        body["node_version"] = version
    resp = admin_client.post(
        "/api/nodes/register",
        headers={"X-Node-API-Key": api_key},
        json=body,
    )
    return node_id, api_key, resp


def test_register_persists_node_version(admin_client):
    """Reported version must land on the node row so the dashboard can show it."""
    node_id, _, resp = _create_and_register(admin_client, version="0.1.0")
    assert resp.status_code == 200

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node.node_version == "0.1.0"
        assert node.version_checked_at is not None
    finally:
        session.close()


def test_register_without_version_is_tolerated(admin_client):
    """Old CloudNodes that pre-date version reporting must still register —
    they just get an update_available hint instead of a 426."""
    node_id, _, resp = _create_and_register(admin_client, version=None)
    assert resp.status_code == 200
    # No version field → row is null but still flagged for an update.
    assert resp.json().get("update_available")  # LATEST is non-empty by default

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node.node_version is None
        assert node.version_checked_at is not None
    finally:
        session.close()


def test_register_rejects_too_old_version(admin_client, monkeypatch):
    """A CloudNode below MIN_SUPPORTED gets HTTP 426 with the install hint."""
    # Bump the floor above the version we'll report.
    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.5.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.5.0")

    _, _, resp = _create_and_register(admin_client, version="0.1.0")
    assert resp.status_code == 426
    detail = resp.json()["detail"]
    assert detail["reported"] == "0.1.0"
    assert detail["min_supported"] == "0.5.0"
    assert detail["latest"] == "0.5.0"
    assert "no longer supported" in detail["message"]


def test_register_too_old_records_error_on_node(admin_client, monkeypatch):
    """A 426 must also stamp last_register_error so the dashboard can show why
    the node is stuck (without making the operator hunt through CloudNode logs)."""
    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.5.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.5.0")

    node_id, _, resp = _create_and_register(admin_client, version="0.1.0")
    assert resp.status_code == 426

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node.last_register_error is not None
        assert "below the minimum" in node.last_register_error
    finally:
        session.close()


def test_register_at_latest_omits_update_available(admin_client, monkeypatch):
    """When the node is current there's no nudge to hand back — keep the
    response payload tight so the field unambiguously means 'newer exists'."""
    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.1.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.1.0")

    _, _, resp = _create_and_register(admin_client, version="0.1.0")
    assert resp.status_code == 200
    assert "update_available" not in resp.json()


def test_register_outdated_includes_update_available(admin_client, monkeypatch):
    """A node behind LATEST but above MIN gets the hint without being rejected."""
    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.1.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.3.0")

    _, _, resp = _create_and_register(admin_client, version="0.2.0")
    assert resp.status_code == 200
    assert resp.json().get("update_available") == "0.3.0"


def test_heartbeat_persists_node_version(admin_client):
    """Heartbeat must keep node_version current so an in-place CloudNode
    upgrade is visible without forcing the operator to re-register."""
    node_id, api_key, _ = _create_and_register(admin_client, version="0.1.0")

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id, "node_version": "0.2.0"},
    )
    assert hb.status_code == 200

    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).first()
        assert node.node_version == "0.2.0"
    finally:
        session.close()


def test_heartbeat_rejects_too_old_version(admin_client, monkeypatch):
    """Same gate on heartbeat as on register — a node downgraded below
    MIN can't pretend it's still healthy."""
    node_id, api_key, _ = _create_and_register(admin_client, version="0.1.0")

    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.5.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.5.0")

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id, "node_version": "0.1.0"},
    )
    assert hb.status_code == 426
    assert hb.json()["detail"]["min_supported"] == "0.5.0"


def test_heartbeat_outdated_returns_update_available(admin_client, monkeypatch):
    """Outdated-but-supported heartbeats get the hint in the response so the
    dashboard can keep the badge fresh between registers."""
    node_id, api_key, _ = _create_and_register(admin_client, version="0.1.0")

    from app.core import versions as versions_mod
    monkeypatch.setattr(versions_mod.settings, "MIN_SUPPORTED_NODE_VERSION", "0.1.0")
    monkeypatch.setattr(versions_mod.settings, "LATEST_NODE_VERSION", "0.4.0")

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id, "node_version": "0.2.0"},
    )
    assert hb.status_code == 200
    assert hb.json().get("update_available") == "0.4.0"


def test_to_dict_exposes_node_version(admin_client):
    """The /api/nodes listing must surface version info so the dashboard
    can render an 'update available' badge without a second fetch."""
    node_id, _, _ = _create_and_register(admin_client, version="0.1.0")

    listing = admin_client.get("/api/nodes").json()
    entry = next(n for n in listing if n["node_id"] == node_id)
    assert entry["node_version"] == "0.1.0"
    assert entry["version_checked_at"]


# ── Plan field on register / heartbeat ───────────────────────────────
#
# The CloudNode renders this as a pill badge in its status bar (e.g.
# ``[ PRO ]``). The field is advisory — enforcement stays server-side.
# See `wire_plan_slug()` and the doc comment on
# `api.types.RegisterResponse.plan` in the cloudnode repo for the full
# contract.


def test_register_response_includes_plan(admin_client):
    """Register response must include ``plan`` so the node can surface a
    pill badge on first registration (before the first heartbeat)."""
    _, _, resp = _create_and_register(admin_client)
    assert resp.status_code == 200
    # With no cached Setting and Clerk unreachable in tests, the org
    # falls back to the free tier — wired as ``"free"`` (no _org suffix).
    assert resp.json().get("plan") == "free"


def test_register_response_plan_reflects_paid_tier(admin_client):
    """A Setting-stored paid plan must flow through to the register
    response so an operator who upgraded before installing the node
    sees the right badge immediately."""
    from app.models.models import Setting
    from tests.conftest import TestSession

    session = TestSession()
    try:
        Setting.set(session, "org_test123", "org_plan", "pro")
        session.commit()
    finally:
        session.close()

    _, _, resp = _create_and_register(admin_client)
    assert resp.status_code == 200
    assert resp.json().get("plan") == "pro"


def test_heartbeat_response_includes_plan(admin_client):
    """Heartbeats must also carry ``plan`` so an operator who upgrades
    or downgrades mid-session sees the badge update without having to
    re-register the node."""
    node_id, api_key, _ = _create_and_register(admin_client)

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id},
    )
    assert hb.status_code == 200
    assert hb.json().get("plan") == "free"


def test_heartbeat_plan_updates_when_setting_changes(admin_client):
    """If the Clerk webhook upgrades an org, the next heartbeat must
    reflect the new plan — no node restart required."""
    from app.models.models import Setting
    from tests.conftest import TestSession

    node_id, api_key, _ = _create_and_register(admin_client)

    # Simulate the Clerk webhook promoting this org to Business.
    session = TestSession()
    try:
        Setting.set(session, "org_test123", "org_plan", "business")
        session.commit()
    finally:
        session.close()

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id},
    )
    assert hb.status_code == 200
    assert hb.json().get("plan") == "business"


def test_heartbeat_reports_disabled_cameras(admin_client):
    """When the backend has suspended some of this node's cameras by plan
    cap, the heartbeat response lists their camera_ids so the CloudNode
    can mark them ``suspended`` in the TUI and stop pushing segments."""
    from app.models.models import Camera, CameraNode
    from tests.conftest import TestSession

    node_id, api_key, _ = _create_and_register(admin_client)

    # Seed two cameras, flag one as disabled_by_plan.
    session = TestSession()
    try:
        node = session.query(CameraNode).filter_by(node_id=node_id).one()
        session.add_all([
            Camera(
                camera_id="cam_suspended",
                org_id=node.org_id,
                node_id=node.id,
                name="Suspended",
                status="online",
                disabled_by_plan=True,
            ),
            Camera(
                camera_id="cam_active",
                org_id=node.org_id,
                node_id=node.id,
                name="Active",
                status="online",
                disabled_by_plan=False,
            ),
        ])
        session.commit()
    finally:
        session.close()

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id},
    )
    assert hb.status_code == 200
    disabled = hb.json().get("disabled_cameras")
    assert disabled == ["cam_suspended"], disabled


def test_heartbeat_disabled_cameras_is_empty_when_none_suspended(admin_client):
    """Happy path: a paid org with no over-cap cameras gets an empty list,
    not a missing field."""
    node_id, api_key, _ = _create_and_register(admin_client)

    hb = admin_client.post(
        "/api/nodes/heartbeat",
        headers={"X-Node-API-Key": api_key},
        json={"node_id": node_id},
    )
    assert hb.status_code == 200
    assert hb.json().get("disabled_cameras") == []
