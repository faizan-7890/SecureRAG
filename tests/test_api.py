from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services.ingestion import DocumentIngestionService
from app.services.rag_service import RAGService, RetrievedChunk


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents = []
        self.ids = []

    def add_documents(self, documents, ids) -> None:
        self.documents.extend(documents)
        self.ids.extend(ids)


class FakeRetrievalStore:
    def __init__(self, results) -> None:
        self.results = results
        self.requested_k = None

    def similarity_search_with_relevance_scores(self, question, k):
        self.requested_k = k
        return self.results


def test_health_check() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_rejects_blank_question() -> None:
    client = TestClient(app)
    response = client.post("/chat", json={"question": ""})

    assert response.status_code == 422


def test_uploads_chunks_and_enriches_text_document(monkeypatch, tmp_path) -> None:
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
    assert vector_store.documents[0].metadata["document_id"]
    assert vector_store.documents[0].metadata["source_sha256"]
    assert vector_store.documents[0].metadata["chunk_index"] == 0
    assert vector_store.ids[0].endswith(":0")


def test_retrieval_filters_low_relevance_and_limits_results(monkeypatch) -> None:
    high = SimpleNamespace(page_content="Relevant leave policy", metadata={"filename": "policy.txt"})
    low = SimpleNamespace(page_content="Unrelated material", metadata={"filename": "other.txt"})
    vector_store = FakeRetrievalStore([(high, 0.88), (low, 0.12)])
    settings = Settings(
        openai_api_key="test-key",
        top_k=1,
        retrieval_candidate_k=5,
        similarity_threshold=0.5,
    )
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: vector_store)

    chunks = service._retrieve("How much annual leave do I get?")

    assert vector_store.requested_k == 5
    assert len(chunks) == 1
    assert chunks[0].document is high
    assert chunks[0].relevance_score == 0.88


def test_citations_include_page_chunk_and_relevance() -> None:
    document = SimpleNamespace(
        page_content="Employees receive 20 days of annual leave.",
        metadata={"filename": "policy.pdf", "page": 2, "chunk_index": 3},
    )
    service = RAGService(Settings(citation_excerpt_chars=100))

    sources = service._sources([RetrievedChunk(document=document, relevance_score=0.8764)])

    assert len(sources) == 1
    assert sources[0].filename == "policy.pdf"
    assert sources[0].page == 2
    assert sources[0].chunk_index == 3
    assert sources[0].relevance_score == 0.876
