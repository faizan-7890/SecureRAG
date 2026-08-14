"""Tests for authentication endpoints."""

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


def test_register_returns_201_and_token(auth_client):
    resp = auth_client.post("/auth/register", json={"username": "newuser01", "password": "StrongPass1!"})
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_returns_409(auth_client):
    auth_client.post("/auth/register", json={"username": "dupuser", "password": "StrongPass1!"})
    resp = auth_client.post("/auth/register", json={"username": "dupuser", "password": "StrongPass1!"})
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


def test_login_with_correct_credentials(auth_client, registered_user):
    username, password, _ = registered_user
    resp = auth_client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_with_wrong_password(auth_client, registered_user):
    username, _, _ = registered_user
    resp = auth_client.post("/auth/login", json={"username": username, "password": "wrong_password"})
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


def test_register_disabled_without_auth_secret():
    """When AUTH_SECRET is not set, registration should return 503."""
    settings = Settings(auth_secret=None)
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        client = TestClient(app)
        resp = client.post("/auth/register", json={"username": "noauth", "password": "StrongPass1!"})
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_register_rejects_short_username(auth_client):
    resp = auth_client.post("/auth/register", json={"username": "ab", "password": "StrongPass1!"})
    assert resp.status_code == 422


def test_register_rejects_short_password(auth_client):
    resp = auth_client.post("/auth/register", json={"username": "validuser", "password": "short"})
    assert resp.status_code == 422


def test_register_bootstrap_admin_rejected(tmp_path):
    """Attempting to register the bootstrap admin username must be rejected with 400."""
    settings = Settings(
        auth_secret="test-secret",
        auth_bootstrap_admin="admin",
        auth_bootstrap_password="AdminPassword123!",
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        client = TestClient(app)
        resp = client.post("/auth/register", json={"username": "admin", "password": "AttackerPassword123!"})
        assert resp.status_code == 400
        assert "reserved" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_bootstrap_admin_login_success(tmp_path):
    """Bootstrap admin can log in with configured bootstrap credentials and receive admin token."""
    settings = Settings(
        auth_secret="test-secret",
        auth_bootstrap_admin="admin",
        auth_bootstrap_password="AdminPassword123!",
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        client = TestClient(app)
        resp = client.post("/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
    finally:
        app.dependency_overrides.pop(get_settings, None)

