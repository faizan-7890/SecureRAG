"""Test bootstrap and shared fixtures for SecureRAG."""

import sys
import types
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Windows uuid-utils shim (must run before any import that triggers chromadb)
# ---------------------------------------------------------------------------

uuid_utils = types.ModuleType("uuid_utils")
compat = types.ModuleType("uuid_utils.compat")
compat.uuid7 = uuid4
uuid_utils.compat = compat
sys.modules["uuid_utils"] = uuid_utils
sys.modules["uuid_utils.compat"] = compat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

from app.core.config import Settings, get_settings
from app.core.security import UserStore
from app.main import app


@pytest.fixture()
def test_settings(tmp_path):
    """Return a Settings instance with auth enabled and isolated paths."""
    return Settings(
        auth_secret="test-secret-key-for-jwt",
        auth_bootstrap_admin=None,
        auth_bootstrap_password=None,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
        openai_api_key="test-key",
    )


@pytest.fixture()
def auth_client(test_settings):
    """TestClient with authentication configured via FastAPI dependency override."""
    app.dependency_overrides[get_settings] = lambda: test_settings
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture()
def registered_user(auth_client):
    """Register a test user and return (username, password, token)."""
    username = f"testuser_{uuid4().hex[:6]}"
    password = "secureP@ss123"
    resp = auth_client.post("/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return username, password, token


@pytest.fixture(autouse=True)
def _clear_user_store():
    """Reset the in-memory user store between tests."""
    UserStore.users = {}
    yield
    UserStore.users = {}
