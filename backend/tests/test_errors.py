"""Tests for the ApiError class + the 422 validation exception handler.

The class itself is small enough to test directly; the handler is wired into
``app.main`` so we exercise it through the FastAPI test client by hitting an
existing endpoint with an invalid body and asserting the rewritten envelope.
"""

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError

# ── ApiError unit tests ────────────────────────────────────────────


def test_apierror_minimal_envelope():
    """Status, code, and message land in the right slots."""
    err = ApiError(404, "camera_not_found", "Camera not found")
    assert err.status_code == 404
    assert err.detail == {"error": "camera_not_found", "message": "Camera not found"}


def test_apierror_extras_flatten_into_detail():
    """Optional kwargs (plan, max_cameras, etc.) sit alongside error/message
    in the same flat dict — matches the existing 402 plan-limit-hit shape so
    the frontend's parser handles both old and new sites identically."""
    err = ApiError(
        402,
        "plan_limit_hit",
        "Camera over the Free plan limit",
        plan="Free",
        max_cameras=5,
        camera_name="Front Door",
    )
    assert err.status_code == 402
    assert err.detail == {
        "error": "plan_limit_hit",
        "message": "Camera over the Free plan limit",
        "plan": "Free",
        "max_cameras": 5,
        "camera_name": "Front Door",
    }


def test_apierror_rejects_reserved_extra_keys():
    """``error`` is envelope-reserved; collisions raise loudly so a typo
    can't silently overwrite the machine-readable code in detail.

    (``message`` is also reserved but Python catches that one earlier with
    a built-in TypeError because it's the third positional parameter — no
    extra check needed for that key.)"""
    with pytest.raises(ValueError, match="reserved envelope field"):
        ApiError(400, "bad_request", "Body invalid", error="something_else")


def test_apierror_serializes_through_fastapi_handler():
    """End-to-end: ApiError raised from a route handler reaches the wire as
    ``{detail: {error, message, ...}}`` — the shape services/api.js parses."""
    app = FastAPI()

    @app.get("/raise")
    def _raise():
        raise ApiError(
            418,
            "im_a_teapot",
            "Cannot brew coffee",
            requested="coffee",
            available=["tea"],
        )

    with TestClient(app) as client:
        resp = client.get("/raise")
    assert resp.status_code == 418
    assert resp.json() == {
        "detail": {
            "error": "im_a_teapot",
            "message": "Cannot brew coffee",
            "requested": "coffee",
            "available": ["tea"],
        },
    }


# ── 422 validation handler integration ─────────────────────────────
#
# We rebuild a fresh FastAPI app for these tests rather than reusing the
# real `app.main.app`. Two reasons:
#   - Adding routes to the live app post-startup falls through to the SPA
#     middleware (returns index.html, not the test endpoint's response).
#   - The validation handler is the unit under test; isolating it from
#     the rest of the production middleware stack makes failures easy to
#     attribute.
# We import the handler function directly from main.py and re-register it
# on the test app so we're testing the same code that ships.


def _make_validation_test_app():
    """Build a fresh FastAPI app with only the validation handler from
    main.py wired in. Used to exercise the 422 → envelope rewrite without
    pulling in the SPA middleware / Clerk / database lifecycle."""
    from fastapi.exceptions import RequestValidationError

    from app.main import validation_exception_handler

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    class Body(BaseModel):
        name: str
        port: int

    @app.post("/validate")
    def _endpoint(body: Body):
        return {"ok": True, "name": body.name}

    return app


def test_validation_error_rewritten_to_apierror_envelope():
    """A request that fails Pydantic validation should come back through the
    same envelope shape as ApiError — error code, human message, and the
    raw Pydantic error list preserved under detail.errors for clients that
    want the per-field breakdown."""
    app = _make_validation_test_app()

    with TestClient(app) as client:
        # Missing required field "port".
        resp = client.post("/validate", json={"name": "x"})

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    body = resp.json()

    assert "detail" in body
    detail = body["detail"]
    assert detail["error"] == "validation_failed"
    assert isinstance(detail["message"], str) and detail["message"]
    # Full per-field list preserved for callers that need it.
    assert isinstance(detail["errors"], list) and detail["errors"]
    first = detail["errors"][0]
    assert "loc" in first and "msg" in first


def test_validation_error_handler_summarises_first_field_in_message():
    """The summary message points at the first failing field so a toast
    can show ``"Field required (name)"`` instead of a generic message."""
    app = _make_validation_test_app()

    with TestClient(app) as client:
        resp = client.post("/validate", json={})

    body = resp.json()
    msg = body["detail"]["message"]
    # Either "name" or "port" — both are missing, ordering depends on Pydantic
    # internals but at least one should appear in the summary.
    assert any(field in msg for field in ("name", "port"))
