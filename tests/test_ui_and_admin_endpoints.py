"""Tests for UI and Admin support endpoints: /auth/me, /auth/users, role update, and /documents/{id}/chunks."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.security import UserStore, create_access_token
from app.main import app
from app.services.ingestion import DocumentRegistry, IngestionResult


@pytest.fixture
def auth_settings(tmp_path):
    return Settings(
        auth_secret="test-secret-key-12345",
        auth_bootstrap_admin="admin",
        auth_bootstrap_password="AdminPassword123!",
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
        bm25_index_path=tmp_path / "chroma" / "bm25_index.json",
    )


@pytest.fixture
def client_with_auth(auth_settings):
    app.dependency_overrides[get_settings] = lambda: auth_settings
    UserStore.users.clear()
    UserStore.add("admin", "AdminPassword123!", "admin")
    UserStore.add("alice", "AlicePassword123!", "user")
    UserStore.add("bob", "BobPassword123!", "user")
    yield TestClient(app)
    app.dependency_overrides.pop(get_settings, None)
    UserStore.users.clear()


def test_get_me_endpoint(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("alice"), auth_settings)
    res = client_with_auth.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == {"username": "alice", "role": "user"}


def test_list_users_as_admin(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("admin"), auth_settings)
    res = client_with_auth.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3
    usernames = [u["username"] for u in data["users"]]
    assert "admin" in usernames
    assert "alice" in usernames


def test_list_users_rejected_for_regular_user(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("alice"), auth_settings)
    res = client_with_auth.get("/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_update_user_role_as_admin(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("admin"), auth_settings)
    res = client_with_auth.patch(
        "/auth/users/alice/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "admin"
    assert UserStore.get("alice")["role"] == "admin"


def test_update_user_role_rejected_for_regular_user(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("bob"), auth_settings)
    res = client_with_auth.patch(
        "/auth/users/alice/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"},
    )
    assert res.status_code == 403


def test_get_document_chunks_not_found(client_with_auth, auth_settings):
    token = create_access_token(UserStore.get("admin"), auth_settings)
    res = client_with_auth.get("/documents/nonexistent-id/chunks", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_get_document_chunks_rbac_access(client_with_auth, auth_settings, monkeypatch):
    class FakeVectorStore:
        def get(self, where, include):
            return {
                "documents": ["Chunk 0 text", "Chunk 1 text"],
                "metadatas": [
                    {"chunk_index": 0, "page": 1, "owner_id": "alice", "allowed_roles": "admin,user"},
                    {"chunk_index": 1, "page": 1, "owner_id": "alice", "allowed_roles": "admin,user"},
                ],
                "ids": ["doc123:0", "doc123:1"],
            }

    from app.services.rag_service import RAGService
    monkeypatch.setattr(RAGService, "_vector_store", lambda self: FakeVectorStore())

    DocumentRegistry.add(
        IngestionResult(
            filename="policy.txt",
            chunks=2,
            document_id="doc123",
            uploaded_at="2026-08-19T00:00:00Z",
            owner_id="alice",
            file_extension=".txt",
            source_sha256="dummy",
            source_size_bytes=100,
        )
    )

    # Alice (owner) can view chunks
    alice_token = create_access_token(UserStore.get("alice"), auth_settings)
    res_alice = client_with_auth.get("/documents/doc123/chunks", headers={"Authorization": f"Bearer {alice_token}"})
    assert res_alice.status_code == 200
    body = res_alice.json()
    assert body["total_chunks"] == 2
    assert body["filename"] == "policy.txt"
    assert len(body["chunks"]) == 2

    # Admin can view chunks
    admin_token = create_access_token(UserStore.get("admin"), auth_settings)
    res_admin = client_with_auth.get("/documents/doc123/chunks", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200

    # Bob (different user) is rejected with 403
    bob_token = create_access_token(UserStore.get("bob"), auth_settings)
    res_bob = client_with_auth.get("/documents/doc123/chunks", headers={"Authorization": f"Bearer {bob_token}"})
    assert res_bob.status_code == 403
