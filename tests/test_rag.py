"""Tests for RAG retrieval, RBAC filtering, and answer generation."""

from types import SimpleNamespace

from app.core.config import Settings
from app.models.schemas import Source
from app.services.rag_service import RAGService, RetrievedChunk


class FakeRetrievalStore:
    def __init__(self, results) -> None:
        self.results = results
        self.requested_k = None

    def similarity_search_with_relevance_scores(self, question, k):
        self.requested_k = k
        return self.results


def _make_doc(filename="doc.txt", page=None, chunk_index=0, owner_id="legacy", content="Some content"):
    meta = {"filename": filename, "chunk_index": chunk_index, "owner_id": owner_id}
    if page is not None:
        meta["page"] = page
    return SimpleNamespace(page_content=content, metadata=meta)


# ---------------------------------------------------------------------------
# Retrieval & RBAC
# ---------------------------------------------------------------------------

def test_retrieve_rbac_admin_sees_all(monkeypatch):
    """Admin users should see all documents regardless of owner."""
    doc_a = _make_doc(owner_id="alice")
    doc_b = _make_doc(owner_id="bob")
    store = FakeRetrievalStore([(doc_a, 0.9), (doc_b, 0.85)])

    settings = Settings(openai_api_key="k", top_k=10, retrieval_candidate_k=10, similarity_threshold=0.3, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    admin_user = {"username": "admin", "role": "admin"}
    chunks = service._retrieve("test", admin_user)
    assert len(chunks) == 2


def test_retrieve_rbac_user_sees_own_and_legacy(monkeypatch):
    """Regular users should only see their own documents and legacy ones."""
    own_doc = _make_doc(owner_id="alice")
    legacy_doc = _make_doc(owner_id="legacy")
    other_doc = _make_doc(owner_id="bob")
    store = FakeRetrievalStore([(own_doc, 0.9), (legacy_doc, 0.85), (other_doc, 0.8)])

    settings = Settings(auth_secret="secret", openai_api_key="k", top_k=10, retrieval_candidate_k=10, similarity_threshold=0.3, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    user = {"username": "alice", "role": "user"}
    chunks = service._retrieve("test", user)
    assert len(chunks) == 2
    owners = {c.document.metadata["owner_id"] for c in chunks}
    assert "bob" not in owners


def test_retrieve_unauthenticated_only_sees_legacy_when_auth_configured(monkeypatch):
    """Unauthenticated queries must only see legacy documents when auth is enabled."""
    alice_doc = _make_doc(owner_id="alice")
    bob_doc = _make_doc(owner_id="bob")
    legacy_doc = _make_doc(owner_id="legacy")
    store = FakeRetrievalStore([(alice_doc, 0.95), (bob_doc, 0.9), (legacy_doc, 0.85)])

    settings = Settings(auth_secret="test-secret", openai_api_key="k", top_k=10, retrieval_candidate_k=10, similarity_threshold=0.3, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    chunks = service._retrieve("test", user=None)
    assert len(chunks) == 1
    assert chunks[0].document.metadata["owner_id"] == "legacy"


def test_retrieve_unauthenticated_sees_all_when_auth_not_configured(monkeypatch):
    """When auth is disabled (AUTH_SECRET=None), unauthenticated queries can see all docs."""
    alice_doc = _make_doc(owner_id="alice")
    bob_doc = _make_doc(owner_id="bob")
    legacy_doc = _make_doc(owner_id="legacy")
    store = FakeRetrievalStore([(alice_doc, 0.95), (bob_doc, 0.9), (legacy_doc, 0.85)])

    settings = Settings(auth_secret=None, openai_api_key="k", top_k=10, retrieval_candidate_k=10, similarity_threshold=0.3, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    chunks = service._retrieve("test", user=None)
    assert len(chunks) == 3



def test_retrieve_respects_top_k(monkeypatch):
    docs = [(_make_doc(content=f"doc{i}"), 0.9 - i * 0.01) for i in range(10)]
    store = FakeRetrievalStore(docs)

    settings = Settings(openai_api_key="k", top_k=3, retrieval_candidate_k=10, similarity_threshold=0.3, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    chunks = service._retrieve("test")
    assert len(chunks) == 3


def test_retrieve_filters_below_threshold(monkeypatch):
    high = _make_doc(content="relevant")
    low = _make_doc(content="irrelevant")
    store = FakeRetrievalStore([(high, 0.9), (low, 0.1)])

    settings = Settings(openai_api_key="k", top_k=10, retrieval_candidate_k=10, similarity_threshold=0.5, enable_hybrid_search=False)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    chunks = service._retrieve("test")
    assert len(chunks) == 1
    assert chunks[0].relevance_score == 0.9


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------

def test_format_context_includes_filenames_and_pages():
    doc_with_page = _make_doc(filename="policy.pdf", page=3, content="Page 3 content")
    doc_no_page = _make_doc(filename="readme.txt", content="Readme content")

    chunks = [
        RetrievedChunk(document=doc_with_page, relevance_score=0.9),
        RetrievedChunk(document=doc_no_page, relevance_score=0.8),
    ]
    context = RAGService._format_context(chunks)
    assert "[Source: policy.pdf, page 3]" in context
    assert "[Source: readme.txt]" in context
    assert "Page 3 content" in context


# ---------------------------------------------------------------------------
# Source deduplication
# ---------------------------------------------------------------------------

def test_sources_deduplicates_identical_chunks():
    doc = _make_doc(filename="doc.txt", page=1, chunk_index=0, content="Same content")
    chunks = [
        RetrievedChunk(document=doc, relevance_score=0.9),
        RetrievedChunk(document=doc, relevance_score=0.9),
    ]
    settings = Settings(citation_excerpt_chars=200)
    sources = RAGService(settings)._sources(chunks)
    assert len(sources) == 1


# ---------------------------------------------------------------------------
# Answer fallback
# ---------------------------------------------------------------------------

def test_answer_fallback_when_no_relevant_chunks(monkeypatch):
    store = FakeRetrievalStore([])
    settings = Settings(openai_api_key="k", top_k=4, retrieval_candidate_k=12, similarity_threshold=0.5)
    service = RAGService(settings)
    monkeypatch.setattr(service, "_vector_store", lambda: store)

    result = service.answer("Anything?")
    assert "could not find" in result.answer.lower()
    assert result.sources == []


# ---------------------------------------------------------------------------
# Deletion & RBAC
# ---------------------------------------------------------------------------

def test_delete_document_rbac_unauthenticated_fails_when_auth_configured(tmp_path):
    import pytest
    from app.services.ingestion import DocumentRegistry, IngestionResult

    doc_id = "test-doc-123"
    DocumentRegistry._records[doc_id] = IngestionResult(
        filename="test.txt",
        chunks=1,
        document_id=doc_id,
        uploaded_at="2026-01-01T00:00:00Z",
        owner_id="alice",
        file_extension=".txt",
        source_sha256="123",
        source_size_bytes=10,
    )

    settings = Settings(
        auth_secret="test-secret",
        chroma_path=tmp_path / "chroma",
        bm25_index_path=tmp_path / "bm25.json",
    )
    service = RAGService(settings)

    with pytest.raises(PermissionError, match="Authentication is required"):
        service.delete_document(doc_id, user=None)

