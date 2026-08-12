"""Tests for M12 — Document Management API (GET /documents, DELETE /documents/{id})
and M13 — Session History API (GET /chat/history/{id}, DELETE /chat/history/{id}).
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services.ingestion import DocumentRegistry, IngestionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(**kwargs) -> IngestionResult:
    defaults = dict(
        filename="test.txt",
        chunks=3,
        document_id=str(uuid4()),
        uploaded_at="2026-01-01T00:00:00+00:00",
        owner_id="legacy",
        file_extension=".txt",
        source_sha256="abc123",
        source_size_bytes=512,
    )
    defaults.update(kwargs)
    return IngestionResult(**defaults)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear DocumentRegistry between tests."""
    DocumentRegistry._records.clear()
    yield
    DocumentRegistry._records.clear()


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------

class TestListDocuments:
    def test_empty_list(self, auth_client):
        resp = auth_client.get("/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["documents"] == []

    def test_lists_ingested_document(self, auth_client):
        result = _make_result(filename="policy.pdf", chunks=10, owner_id="legacy")
        DocumentRegistry.add(result)

        resp = auth_client.get("/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        doc = body["documents"][0]
        assert doc["filename"] == "policy.pdf"
        assert doc["chunks"] == 10
        assert doc["document_id"] == result.document_id

    def test_lists_multiple_documents(self, auth_client):
        for i in range(3):
            DocumentRegistry.add(_make_result(filename=f"doc{i}.txt", document_id=str(uuid4())))

        resp = auth_client.get("/documents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_regular_user_sees_own_and_legacy_docs(self, auth_client, registered_user):
        username, _, token = registered_user

        DocumentRegistry.add(_make_result(owner_id=username, document_id=str(uuid4())))
        DocumentRegistry.add(_make_result(owner_id="other_user", document_id=str(uuid4())))
        DocumentRegistry.add(_make_result(owner_id="legacy", document_id=str(uuid4())))

        resp = auth_client.get("/documents", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        docs = resp.json()["documents"]
        owners = {d["owner_id"] for d in docs}
        assert "other_user" not in owners


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id}
# ---------------------------------------------------------------------------

class TestDeleteDocument:
    def test_delete_nonexistent_returns_404(self, auth_client):
        resp = auth_client.delete("/documents/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_existing_document(self, auth_client):
        result = _make_result(filename="remove_me.txt", owner_id="legacy")
        DocumentRegistry.add(result)
        assert DocumentRegistry.get(result.document_id) is not None

        with (
            patch("app.services.rag_service.RAGService._vector_store") as mock_vs,
            patch("app.services.rag_service.RAGService._bm25_index"),
        ):
            mock_vs.return_value.get.return_value = {"ids": []}
            resp = auth_client.delete(f"/documents/{result.document_id}")

        assert resp.status_code == 204
        assert DocumentRegistry.get(result.document_id) is None

    def test_user_cannot_delete_other_users_document(self, auth_client, test_settings, registered_user):
        username, _, token = registered_user
        result = _make_result(owner_id="other_user")
        DocumentRegistry.add(result)

        resp = auth_client.delete(
            f"/documents/{result.document_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_can_delete_any_document(self, test_settings):
        from app.core.security import UserStore, create_access_token, _hash_password

        UserStore.users["admin_test"] = {
            "username": "admin_test",
            "password": _hash_password("adminpassword"),
            "role": "admin",
        }
        admin_token = create_access_token(UserStore.users["admin_test"], test_settings)

        result = _make_result(owner_id="some_user")
        DocumentRegistry.add(result)

        app.dependency_overrides[get_settings] = lambda: test_settings
        client = TestClient(app)
        try:
            with (
                patch("app.services.rag_service.RAGService._vector_store") as mock_vs,
                patch("app.services.rag_service.RAGService._bm25_index"),
            ):
                mock_vs.return_value.get.return_value = {"ids": []}
                resp = client.delete(
                    f"/documents/{result.document_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
            assert resp.status_code == 204
        finally:
            app.dependency_overrides.pop(get_settings, None)
            UserStore.users.pop("admin_test", None)


# ---------------------------------------------------------------------------
# GET /chat/history/{session_id} and DELETE
# ---------------------------------------------------------------------------

class TestSessionHistory:
    def test_returns_empty_for_unknown_session(self, auth_client):
        resp = auth_client.get("/chat/history/unknown-session-id")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "unknown-session-id"
        assert body["messages"] == []
        assert body["total"] == 0

    def test_returns_messages_for_known_session(self, auth_client):
        from app.core.session_store import SessionStore

        session_id = uuid4().hex
        SessionStore.add_turn(session_id, "Hello", "Hi there!", max_messages=10)

        resp = auth_client.get(f"/chat/history/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session_id
        assert body["total"] == 2
        roles = [m["role"] for m in body["messages"]]
        assert "user" in roles
        assert "assistant" in roles

    def test_delete_clears_session(self, auth_client):
        from app.core.session_store import SessionStore

        session_id = uuid4().hex
        SessionStore.add_turn(session_id, "Q", "A", max_messages=10)
        assert SessionStore.get_history(session_id)

        resp = auth_client.delete(f"/chat/history/{session_id}")
        assert resp.status_code == 204
        assert SessionStore.get_history(session_id) == []

    def test_delete_nonexistent_session_is_idempotent(self, auth_client):
        resp = auth_client.delete("/chat/history/does-not-exist")
        assert resp.status_code == 204
