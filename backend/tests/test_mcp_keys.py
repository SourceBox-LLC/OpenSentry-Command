"""MCP API key management tests."""


def test_create_mcp_key(admin_client):
    """Admin can create an MCP API key."""
    resp = admin_client.post("/api/mcp/keys?name=Test%20Key")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["key"].startswith("osc_")
    assert len(data["key"]) == 36  # "osc_" + 32 hex chars
    assert "warning" in data


def test_list_mcp_keys(admin_client):
    """Admin can list MCP keys (without plaintext values)."""
    admin_client.post("/api/mcp/keys?name=Key1")
    admin_client.post("/api/mcp/keys?name=Key2")

    resp = admin_client.get("/api/mcp/keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 2
    # Should not contain the actual key value
    for key in keys:
        assert "key" not in key
        assert "key_hash" not in key
        assert "name" in key


def test_revoke_mcp_key(admin_client):
    """Admin can revoke an MCP key."""
    create_resp = admin_client.post("/api/mcp/keys?name=Temp")
    key_id = create_resp.json()["id"]

    revoke_resp = admin_client.delete(f"/api/mcp/keys/{key_id}")
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["success"] is True

    # Revoked key should not appear in list
    list_resp = admin_client.get("/api/mcp/keys")
    assert len(list_resp.json()) == 0


def test_revoke_nonexistent_key(admin_client):
    """Revoking a non-existent key returns 404."""
    resp = admin_client.delete("/api/mcp/keys/9999")
    assert resp.status_code == 404
