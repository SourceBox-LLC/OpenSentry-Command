"""Basic health and security header tests."""


def test_health_endpoint(unauthenticated_client):
    """Health check should always return 200."""
    resp = unauthenticated_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_security_headers(unauthenticated_client):
    """All responses should include security headers."""
    resp = unauthenticated_client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")
