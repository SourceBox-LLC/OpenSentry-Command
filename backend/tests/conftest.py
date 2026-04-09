"""
Shared test fixtures for OpenSentry backend tests.

Sets up an in-memory SQLite database and a FastAPI test client
with Clerk auth bypassed (mocked).
"""

import hashlib
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Must set env vars BEFORE importing app modules so config.py picks them up.
# Use in-memory DB so main.py startup code doesn't touch any real files.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("CLERK_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("CLERK_PUBLISHABLE_KEY", "pk_test_fake")
os.environ.setdefault("CLERK_JWKS_URL", "https://fake.clerk.accounts.dev/.well-known/jwks.json")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "fake")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "fake")
os.environ.setdefault("AWS_ENDPOINT_URL_S3", "https://fake.s3.endpoint")
os.environ.setdefault("TIGRIS_BUCKET_NAME", "test-bucket")

from app.core.auth import AuthUser
from app.core.database import Base, engine, get_db
from app.main import app


# Reuse the app's engine (which is now in-memory thanks to DATABASE_URL override)
TestSession = sessionmaker(bind=engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass  # StaticPool + background threads can cause benign rollback errors


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_db():
    """Clear all table data between tests (tables created once at import)."""
    # Truncate all tables instead of drop/recreate to avoid
    # StaticPool rollback issues with in-memory SQLite.
    session = TestSession()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    """Direct DB session for test setup/assertions."""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


def _make_admin_user(org_id="org_test123"):
    return AuthUser(
        user_id="user_test123",
        org_id=org_id,
        org_role="org:admin",
        org_permissions=["org:admin:admin", "org:cameras:manage_cameras", "org:cameras:view_cameras"],
        email="admin@test.com",
        username="testadmin",
        plan="pro",
        features=["admin", "cameras"],
    )


def _make_viewer_user(org_id="org_test123"):
    return AuthUser(
        user_id="user_viewer456",
        org_id=org_id,
        org_role="org:member",
        org_permissions=["org:cameras:view_cameras"],
        email="viewer@test.com",
        username="testviewer",
        plan="pro",
        features=["cameras"],
    )


@pytest.fixture
def admin_client():
    """Test client authenticated as an admin user."""
    from app.core.auth import require_admin, get_current_user

    admin = _make_admin_user()
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_current_user] = lambda: admin

    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def viewer_client():
    """Test client authenticated as a viewer user."""
    from app.core.auth import require_view, get_current_user

    viewer = _make_viewer_user()
    app.dependency_overrides[require_view] = lambda: viewer
    app.dependency_overrides[get_current_user] = lambda: viewer

    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(require_view, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthenticated_client():
    """Test client with no auth overrides."""
    return TestClient(app)
