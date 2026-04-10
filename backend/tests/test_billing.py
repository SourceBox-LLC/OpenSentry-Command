"""Billing enforcement and org cleanup tests."""

from app.models.models import Setting, CameraNode, CameraGroup, McpApiKey


def test_past_due_blocks_node_creation(admin_client, db):
    """Past-due orgs cannot create new nodes."""
    Setting.set(db, "org_test123", "payment_past_due", "true")

    resp = admin_client.post("/api/nodes", json={"name": "Blocked Node"})
    assert resp.status_code == 402
    assert "past due" in resp.json()["detail"].lower()


def test_past_due_blocks_mcp_key_creation(admin_client, db):
    """Past-due orgs cannot create new MCP keys."""
    Setting.set(db, "org_test123", "payment_past_due", "true")

    resp = admin_client.post("/api/mcp/keys", params={"name": "Blocked Key"})
    assert resp.status_code == 402
    assert "past due" in resp.json()["detail"].lower()


def test_past_due_allows_reads(admin_client, db):
    """Past-due orgs can still read their data."""
    Setting.set(db, "org_test123", "payment_past_due", "true")

    # Listing nodes should still work
    resp = admin_client.get("/api/nodes")
    assert resp.status_code == 200

    # Plan info should still work (and show past_due flag)
    resp = admin_client.get("/api/nodes/plan")
    assert resp.status_code == 200
    assert resp.json()["payment_past_due"] is True


def test_past_due_cleared_allows_creation(admin_client, db):
    """Once past-due is cleared, node creation works again."""
    Setting.set(db, "org_test123", "payment_past_due", "true")
    resp = admin_client.post("/api/nodes", json={"name": "Blocked"})
    assert resp.status_code == 402

    # Clear the flag (simulates successful payment webhook)
    Setting.set(db, "org_test123", "payment_past_due", "false")
    resp = admin_client.post("/api/nodes", json={"name": "Allowed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Allowed"
