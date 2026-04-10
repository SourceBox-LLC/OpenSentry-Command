"""Node management endpoint tests."""


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
