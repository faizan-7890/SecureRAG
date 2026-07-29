from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.ingestion import DocumentIngestionService


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents = []
        self.ids = []

    def add_documents(self, documents, ids) -> None:
        self.documents.extend(documents)
        self.ids.extend(ids)


def test_health_check() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_rejects_blank_question() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"question": ""})

    assert response.status_code == 422


def test_uploads_and_chunks_text_document(monkeypatch, tmp_path) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    vector_store = FakeVectorStore()
    monkeypatch.setattr(
        DocumentIngestionService, "_vector_store", lambda self: vector_store
    )

    client = TestClient(app)
    response = client.post(
        "/documents/upload",
        files={"file": ("policy.txt", b"Employees receive 20 days of annual leave.", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Document ingested"
    assert response.json()["filename"] == "policy.txt"
    assert response.json()["chunks"] == 1
    assert vector_store.documents[0].metadata["filename"] == "policy.txt"
