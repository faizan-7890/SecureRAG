"""Tests for document upload and ingestion."""

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services.ingestion import DocumentIngestionService


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents = []
        self.ids = []

    def add_documents(self, documents, ids) -> None:
        self.documents.extend(documents)
        self.ids.extend(ids)


def test_upload_rejects_unsupported_type():
    client = TestClient(app)
    resp = client.post(
        "/documents/upload",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "supported" in resp.json()["detail"].lower()


def test_upload_rejects_empty_file():
    client = TestClient(app)
    resp = client.post(
        "/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_txt_creates_chunks(monkeypatch, tmp_path):
    settings = Settings(upload_dir=tmp_path / "uploads")
    app.dependency_overrides[get_settings] = lambda: settings
    vector_store = FakeVectorStore()
    monkeypatch.setattr(DocumentIngestionService, "_vector_store", lambda self: vector_store)

    try:
        client = TestClient(app)
        resp = client.post(
            "/documents/upload",
            files={"file": ("readme.txt", b"Hello world. This is a test document.", "text/plain")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["message"] == "Document ingested"
        assert body["filename"] == "readme.txt"
        assert body["chunks"] >= 1
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_upload_markdown_creates_chunks(monkeypatch, tmp_path):
    settings = Settings(upload_dir=tmp_path / "uploads")
    app.dependency_overrides[get_settings] = lambda: settings
    vector_store = FakeVectorStore()
    monkeypatch.setattr(DocumentIngestionService, "_vector_store", lambda self: vector_store)

    content = b"# Title\n\nThis is markdown content with some text.\n\n## Section\n\nMore text here."
    try:
        client = TestClient(app)
        resp = client.post(
            "/documents/upload",
            files={"file": ("notes.md", content, "text/markdown")},
        )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "notes.md"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_chunk_metadata_is_complete(monkeypatch, tmp_path):
    settings = Settings(upload_dir=tmp_path / "uploads")
    app.dependency_overrides[get_settings] = lambda: settings
    vector_store = FakeVectorStore()
    monkeypatch.setattr(DocumentIngestionService, "_vector_store", lambda self: vector_store)

    try:
        client = TestClient(app)
        client.post(
            "/documents/upload",
            files={"file": ("policy.txt", b"Employees receive 20 days of annual leave.", "text/plain")},
        )

        assert len(vector_store.documents) >= 1
        meta = vector_store.documents[0].metadata
        assert "document_id" in meta
        assert "chunk_index" in meta
        assert "source_sha256" in meta
        assert "uploaded_at" in meta
        assert meta["filename"] == "policy.txt"
        assert meta["owner_id"] == "legacy"  # no auth user
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_upload_with_auth_sets_owner(monkeypatch, tmp_path, auth_client, registered_user):
    username, _, token = registered_user
    # auth_client already has test_settings overridden; update upload_dir
    vector_store = FakeVectorStore()
    monkeypatch.setattr(DocumentIngestionService, "_vector_store", lambda self: vector_store)

    resp = auth_client.post(
        "/documents/upload",
        files={"file": ("secret.txt", b"Top secret content.", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    meta = vector_store.documents[0].metadata
    assert meta["owner_id"] == username
