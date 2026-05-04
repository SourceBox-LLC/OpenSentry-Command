"""MCP API key management tests — includes per-key tool scoping."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from app.mcp.server import (
    MCP_ALL_TOOLS,
    MCP_READ_TOOLS,
    MCP_WRITE_TOOLS,
    ScopeMiddleware,
    compute_allowed_tools,
)
from app.models.models import McpApiKey


def test_create_mcp_key(admin_client):
    """Admin can create an MCP API key (default scope = all)."""
    resp = admin_client.post("/api/mcp/keys", json={"name": "Test Key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["key"].startswith("osc_")
    assert len(data["key"]) == 36  # "osc_" + 32 hex chars
    assert data["scope_mode"] == "all"
    assert data["scope_tools"] == []
    assert "warning" in data


def test_list_mcp_keys(admin_client):
    """Admin can list MCP keys (without plaintext values)."""
    admin_client.post("/api/mcp/keys", json={"name": "Key1"})
    admin_client.post("/api/mcp/keys", json={"name": "Key2"})

    resp = admin_client.get("/api/mcp/keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 2
    # Should not contain the actual key value
    for key in keys:
        assert "key" not in key
        assert "key_hash" not in key
        assert "name" in key
        assert key["scope_mode"] == "all"
        assert key["scope_tools"] == []


def test_revoke_mcp_key(admin_client):
    """Admin can revoke an MCP key."""
    create_resp = admin_client.post("/api/mcp/keys", json={"name": "Temp"})
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


# ── Audit notification emission ────────────────────────────────────

def test_create_mcp_key_emits_audit_notification(admin_client, db):
    """Creating an MCP key fires a ``mcp_key_created`` notification
    so admins can spot "who just got programmatic access to my
    cameras?" via the bell-icon panel and (when EMAIL_ENABLED)
    via email.  Audit-trail companion to the existing AuditLog row."""
    from app.models.models import Notification

    resp = admin_client.post("/api/mcp/keys", json={"name": "Audit Probe"})
    assert resp.status_code == 200

    notifs = (
        db.query(Notification)
        .filter_by(kind="mcp_key_created", org_id="org_test123")
        .all()
    )
    assert len(notifs) == 1
    n = notifs[0]
    assert n.audience == "admin"  # security signal — admins only
    assert n.severity == "warning"
    # Title + body include the key name so the email subject is
    # immediately recognisable in the inbox preview.
    assert "Audit Probe" in n.title
    assert "Audit Probe" in n.body
    # Meta carries the key_id for any UI that wants to deep-link.
    import json as _json
    meta = _json.loads(n.meta_json)
    assert meta["key_id"] == resp.json()["id"]


def test_revoke_mcp_key_emits_audit_notification(admin_client, db):
    """Revoking an MCP key fires the paired ``mcp_key_revoked``
    notification so the audit trail is symmetric."""
    from app.models.models import Notification

    create_resp = admin_client.post("/api/mcp/keys", json={"name": "Revoke Me"})
    key_id = create_resp.json()["id"]

    admin_client.delete(f"/api/mcp/keys/{key_id}")

    revoked_notifs = (
        db.query(Notification)
        .filter_by(kind="mcp_key_revoked", org_id="org_test123")
        .all()
    )
    assert len(revoked_notifs) == 1
    n = revoked_notifs[0]
    assert n.audience == "admin"
    # Lower severity than create — revoking is the safe direction.
    assert n.severity == "info"
    assert "Revoke Me" in n.title


def test_mcp_key_notification_failure_does_not_break_endpoint(admin_client, db, monkeypatch):
    """The notification emit is wrapped in try/except — a failure in
    the notification path must NOT break the MCP key API call.
    The audit log row is the load-bearing record; the notification
    is best-effort companion."""
    from app.api import notifications as notifications_mod

    def boom(**kwargs):
        raise RuntimeError("notifications system having a fit")
    monkeypatch.setattr(notifications_mod, "create_notification", boom)

    # The key creation should still succeed even though notification
    # emission throws.
    resp = admin_client.post("/api/mcp/keys", json={"name": "Resilience"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Resilience"


# ──────────────────────────────────────────────────────────────────
# Per-key tool scoping — unit + endpoint tests
# ──────────────────────────────────────────────────────────────────


def test_compute_allowed_tools_all():
    """``all`` mode grants every tool, regardless of scope_tools value."""
    assert compute_allowed_tools("all", None) == MCP_ALL_TOOLS
    assert compute_allowed_tools(None, None) == MCP_ALL_TOOLS
    assert compute_allowed_tools("all", ["list_cameras"]) == MCP_ALL_TOOLS


def test_compute_allowed_tools_readonly():
    """``readonly`` mode grants only read tools."""
    allowed = compute_allowed_tools("readonly", None)
    assert allowed == MCP_READ_TOOLS
    # No write tool leaks in.
    assert not (allowed & MCP_WRITE_TOOLS)


def test_compute_allowed_tools_custom():
    """``custom`` mode is intersection with known tools — unknowns get dropped."""
    allowed = compute_allowed_tools("custom", ["list_cameras", "bogus_tool"])
    assert allowed == frozenset({"list_cameras"})

    # Empty list → empty set (nothing allowed; key is effectively muted).
    assert compute_allowed_tools("custom", []) == frozenset()
    assert compute_allowed_tools("custom", None) == frozenset()


def test_compute_allowed_tools_unknown_mode_defaults_to_all():
    """Unexpected mode values shouldn't lock users out — fall back to full access."""
    assert compute_allowed_tools("weird", None) == MCP_ALL_TOOLS


def test_create_mcp_key_readonly_scope(admin_client):
    """Readonly keys persist with scope_mode=readonly and no scope_tools."""
    resp = admin_client.post(
        "/api/mcp/keys",
        json={"name": "Viewer Agent", "scope_mode": "readonly"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope_mode"] == "readonly"
    assert data["scope_tools"] == []


def test_create_mcp_key_custom_scope(admin_client):
    """Custom keys persist the explicit tool list."""
    resp = admin_client.post(
        "/api/mcp/keys",
        json={
            "name": "Incident Triage",
            "scope_mode": "custom",
            "scope_tools": ["list_cameras", "create_incident", "add_observation"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope_mode"] == "custom"
    assert set(data["scope_tools"]) == {
        "list_cameras",
        "create_incident",
        "add_observation",
    }

    # list endpoint reflects the stored scope
    list_resp = admin_client.get("/api/mcp/keys")
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["scope_mode"] == "custom"
    assert set(listed[0]["scope_tools"]) == {
        "list_cameras",
        "create_incident",
        "add_observation",
    }


def test_create_mcp_key_custom_requires_tools(admin_client):
    """``custom`` mode without scope_tools is rejected with a 400."""
    resp = admin_client.post(
        "/api/mcp/keys",
        json={"name": "Broken", "scope_mode": "custom"},
    )
    assert resp.status_code == 400
    assert "scope_tools" in resp.json()["detail"]


def test_create_mcp_key_custom_rejects_unknown_tools(admin_client):
    """Unknown tool names cannot be granted via the custom scope."""
    resp = admin_client.post(
        "/api/mcp/keys",
        json={
            "name": "Typo",
            "scope_mode": "custom",
            "scope_tools": ["list_cameras", "not_a_real_tool"],
        },
    )
    assert resp.status_code == 400
    assert "not_a_real_tool" in resp.json()["detail"]


def test_create_mcp_key_rejects_bad_mode(admin_client):
    """Invalid scope_mode is rejected by the Pydantic validator (422)."""
    resp = admin_client.post(
        "/api/mcp/keys",
        json={"name": "Bad", "scope_mode": "superuser"},
    )
    assert resp.status_code == 422


def test_list_mcp_tools_catalog(admin_client):
    """The catalog endpoint returns every known tool grouped by category."""
    resp = admin_client.get("/api/mcp/tools")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(MCP_ALL_TOOLS)

    read_names = {t["name"] for t in body["read"]}
    write_names = {t["name"] for t in body["write"]}
    assert read_names == set(MCP_READ_TOOLS)
    assert write_names == set(MCP_WRITE_TOOLS)
    assert read_names.isdisjoint(write_names)

    # Every entry has the shape we tell the UI to expect.
    for tool in body["read"] + body["write"]:
        assert "name" in tool
        assert "description" in tool
        assert tool["category"] in {"read", "write"}


# ──────────────────────────────────────────────────────────────────
# ScopeMiddleware — directly exercised to verify list filter + call gate
# ──────────────────────────────────────────────────────────────────


def _insert_key(db, *, raw_key: str, scope_mode: str, scope_tools: list[str] | None = None):
    """Seed an ``McpApiKey`` with the given scope for middleware tests."""
    key = McpApiKey(
        org_id="org_test123",
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        name="test",
        scope_mode=scope_mode,
        scope_tools=json.dumps(scope_tools) if scope_tools else None,
    )
    db.add(key)
    db.commit()
    return key


def _tool(name: str) -> SimpleNamespace:
    """Minimal stand-in for a fastmcp.Tool — middleware only reads ``.name``."""
    return SimpleNamespace(name=name)


async def _run_on_list_tools(middleware, returned_tools):
    """Invoke ``on_list_tools`` with a fake call_next and headers context."""

    async def call_next(_ctx):
        return returned_tools

    return await middleware.on_list_tools(context=SimpleNamespace(), call_next=call_next)


async def _run_on_call_tool(middleware, tool_name):
    """Invoke ``on_call_tool`` with a fake call_next that records if it ran."""
    ran = {"value": False}

    async def call_next(_ctx):
        ran["value"] = True
        return "ok"

    ctx = SimpleNamespace(message=SimpleNamespace(name=tool_name))
    result = await middleware.on_call_tool(context=ctx, call_next=call_next)
    return result, ran["value"]


@pytest.mark.asyncio
async def test_scope_middleware_list_filters_readonly(db):
    """``on_list_tools`` hides write tools for a read-only key."""
    _insert_key(db, raw_key="osc_ro", scope_mode="readonly")

    tools = [_tool("list_cameras"), _tool("create_incident"), _tool("get_camera")]
    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_ro"},
    ):
        filtered = await _run_on_list_tools(ScopeMiddleware(), tools)

    names = {t.name for t in filtered}
    assert names == {"list_cameras", "get_camera"}


@pytest.mark.asyncio
async def test_scope_middleware_list_no_filter_when_all(db):
    """``all`` mode passes the full tool list through unchanged."""
    _insert_key(db, raw_key="osc_all", scope_mode="all")

    tools = [_tool("list_cameras"), _tool("create_incident")]
    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_all"},
    ):
        filtered = await _run_on_list_tools(ScopeMiddleware(), tools)

    assert {t.name for t in filtered} == {"list_cameras", "create_incident"}


@pytest.mark.asyncio
async def test_scope_middleware_list_passes_through_when_unknown_token(db):
    """No key match → don't silently drop tools; let ``_auth`` error later."""
    tools = [_tool("list_cameras"), _tool("create_incident")]
    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_ghost"},
    ):
        filtered = await _run_on_list_tools(ScopeMiddleware(), tools)

    assert {t.name for t in filtered} == {"list_cameras", "create_incident"}


@pytest.mark.asyncio
async def test_scope_middleware_call_rejects_disallowed(db):
    """A read-only key cannot call a write tool — raises ToolError, call_next skipped."""
    _insert_key(db, raw_key="osc_ro2", scope_mode="readonly")

    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_ro2"},
    ):
        with pytest.raises(ToolError) as exc:
            await _run_on_call_tool(ScopeMiddleware(), "create_incident")

    assert "create_incident" in str(exc.value)


@pytest.mark.asyncio
async def test_scope_middleware_call_allows_permitted(db):
    """A read-only key can call a read tool — call_next runs."""
    _insert_key(db, raw_key="osc_ro3", scope_mode="readonly")

    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_ro3"},
    ):
        result, ran = await _run_on_call_tool(ScopeMiddleware(), "list_cameras")

    assert result == "ok"
    assert ran is True


@pytest.mark.asyncio
async def test_scope_middleware_custom_honors_exact_list(db):
    """Custom scope gates exactly the named tools."""
    _insert_key(
        db,
        raw_key="osc_custom",
        scope_mode="custom",
        scope_tools=["list_cameras", "create_incident"],
    )

    tools = [
        _tool("list_cameras"),
        _tool("get_camera"),
        _tool("create_incident"),
        _tool("finalize_incident"),
    ]
    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_custom"},
    ):
        filtered = await _run_on_list_tools(ScopeMiddleware(), tools)
        _, allowed_ran = await _run_on_call_tool(ScopeMiddleware(), "create_incident")
        with pytest.raises(ToolError):
            await _run_on_call_tool(ScopeMiddleware(), "get_camera")

    assert {t.name for t in filtered} == {"list_cameras", "create_incident"}
    assert allowed_ran is True


@pytest.mark.asyncio
async def test_scope_middleware_ignores_revoked_keys(db):
    """Revoked keys behave as if unknown — tools pass through, downstream auth errors."""
    key = _insert_key(db, raw_key="osc_rev", scope_mode="readonly")
    key.revoked = True
    db.commit()

    tools = [_tool("list_cameras"), _tool("create_incident")]
    with patch(
        "app.mcp.server.get_http_headers",
        return_value={"authorization": "Bearer osc_rev"},
    ):
        filtered = await _run_on_list_tools(ScopeMiddleware(), tools)
        _, ran = await _run_on_call_tool(ScopeMiddleware(), "create_incident")

    assert {t.name for t in filtered} == {"list_cameras", "create_incident"}
    assert ran is True  # middleware didn't block — _auth would reject later
