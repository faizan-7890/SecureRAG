"""Tests for Hybrid Search, BM25 Index, Reciprocal Rank Fusion, and Multi-Query Expansion."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from langchain_core.documents import Document

from app.core.config import Settings
from app.services.hybrid_search import (
    BM25Index,
    MultiQueryExpander,
    _tokenize,
    reciprocal_rank_fusion,
)
from app.services.rag_service import RetrievedChunk


def test_tokenize_basic() -> None:
    tokens = _tokenize("Hello, World! SecureRAG 2026-v2.")
    assert tokens == ["hello", "world", "securerag", "2026", "v2"]


def test_bm25_empty_index() -> None:
    index = BM25Index()
    assert index.total_docs == 0
    results = index.search("anything")
    assert results == []


def test_bm25_add_and_search() -> None:
    index = BM25Index()
    docs = [
        Document(
            page_content="The annual leave entitlement is 20 days per calendar year.",
            metadata={"filename": "policy.txt", "chunk_index": 0, "owner_id": "alice"},
        ),
        Document(
            page_content="Sick leave provides 10 days of paid absence per year.",
            metadata={"filename": "policy.txt", "chunk_index": 1, "owner_id": "alice"},
        ),
        Document(
            page_content="Remote work is allowed up to 3 days per week with manager approval.",
            metadata={"filename": "policy.txt", "chunk_index": 2, "owner_id": "bob"},
        ),
    ]
    index.add_documents(docs)

    assert index.total_docs == 3
    assert "leave" in index.doc_freqs
    assert index.doc_freqs["leave"] == 2  # appears in doc 0 and doc 1

    # Search for "sick leave"
    results = index.search("sick leave", top_k=2)
    assert len(results) >= 1
    top_doc, score = results[0]
    assert "Sick leave provides 10 days" in top_doc.page_content
    assert score > 0.0


def test_bm25_rbac_filtering() -> None:
    index = BM25Index()
    docs = [
        Document(
            page_content="Confidential financial report for Q4 2025.",
            metadata={"filename": "finance.txt", "chunk_index": 0, "owner_id": "alice"},
        ),
        Document(
            page_content="Marketing strategy and public announcements.",
            metadata={"filename": "marketing.txt", "chunk_index": 0, "owner_id": "bob"},
        ),
        Document(
            page_content="General company holiday schedule.",
            metadata={"filename": "general.txt", "chunk_index": 0, "owner_id": "legacy"},
        ),
    ]
    index.add_documents(docs)

    # Bob searches for financial report
    bob_user = {"username": "bob", "role": "user"}
    bob_results = index.search("financial report", user=bob_user)
    # Bob should not see Alice's document
    assert len(bob_results) == 0

    # Alice searches for financial report
    alice_user = {"username": "alice", "role": "user"}
    alice_results = index.search("financial report", user=alice_user)
    assert len(alice_results) == 1
    assert "Confidential financial" in alice_results[0][0].page_content

    # Admin searches for financial report
    admin_user = {"username": "superadmin", "role": "admin"}
    admin_results = index.search("financial report", user=admin_user)
    assert len(admin_results) == 1

    # Bob can see legacy general document
    legacy_results = index.search("holiday schedule", user=bob_user)
    assert len(legacy_results) == 1

    # Anonymous user with auth_enabled=True only sees legacy documents
    anon_auth_results = index.search("financial report", user=None, auth_enabled=True)
    assert len(anon_auth_results) == 0
    anon_legacy_results = index.search("holiday schedule", user=None, auth_enabled=True)
    assert len(anon_legacy_results) == 1

    # Anonymous user with auth_enabled=False (no auth configured) sees all documents
    anon_noauth_results = index.search("financial report", user=None, auth_enabled=False)
    assert len(anon_noauth_results) == 1


def test_bm25_save_and_load(tmp_path: Path) -> None:
    index_file = tmp_path / "bm25_index.json"
    index = BM25Index()
    docs = [
        Document(
            page_content="Acme compliance guidelines for HIPAA regulations.",
            metadata={"filename": "hipaa.txt", "chunk_index": 0, "chunk_id": "c1"},
        ),
    ]
    index.add_documents(docs, ids=["c1"])
    index.save(index_file)

    assert index_file.exists()

    loaded = BM25Index.load(index_file)
    assert loaded.total_docs == 1
    assert loaded.documents[0]["id"] == "c1"
    results = loaded.search("HIPAA")
    assert len(results) == 1
    assert "HIPAA" in results[0][0].page_content


def test_reciprocal_rank_fusion_logic() -> None:
    doc1 = Document(page_content="Doc 1 content", metadata={"chunk_id": "doc1"})
    doc2 = Document(page_content="Doc 2 content", metadata={"chunk_id": "doc2"})
    doc3 = Document(page_content="Doc 3 content", metadata={"chunk_id": "doc3"})

    dense = [
        RetrievedChunk(document=doc1, relevance_score=0.9),
        RetrievedChunk(document=doc2, relevance_score=0.7),
    ]
    sparse = [
        (doc2, 4.5),  # Doc 2 is rank 1 in sparse
        (doc3, 2.1),  # Doc 3 is rank 2 in sparse
    ]

    fused = reciprocal_rank_fusion(
        dense_results=dense,
        sparse_results=sparse,
        rrf_k=60,
        dense_weight=0.6,
        sparse_weight=0.4,
    )

    assert len(fused) == 3
    # doc2 appeared in both dense (rank 2) and sparse (rank 1), so it should rank first
    # Dense rank 2: 0.6/(60+2) = 0.009677
    # Sparse rank 1: 0.4/(60+1) = 0.006557
    # Total for doc2: 0.016234
    # Total for doc1 (dense rank 1 only): 0.6/(60+1) = 0.009836
    # Total for doc3 (sparse rank 2 only): 0.4/(60+2) = 0.006451
    assert fused[0].document.metadata["chunk_id"] == "doc2"
    assert fused[1].document.metadata["chunk_id"] == "doc1"
    assert fused[2].document.metadata["chunk_id"] == "doc3"

    for chunk in fused:
        assert 0.0 <= chunk.relevance_score <= 1.0


def test_multi_query_expander_fallback() -> None:
    # When no API key is provided, falls back to original question
    settings = Settings(openai_api_key=None)
    variations = MultiQueryExpander.expand("What is the refund policy?", settings, count=3)
    assert variations == ["What is the refund policy?"]


class FakeVectorStore:
    def __init__(self) -> None:
        self.documents = []
        self.ids = []

    def add_documents(self, documents, ids) -> None:
        self.documents.extend(documents)
        self.ids.extend(ids)

    def similarity_search_with_relevance_scores(self, question, k):
        return []


def test_ingestion_and_hybrid_retrieval(tmp_path: Path, monkeypatch) -> None:
    from app.services.ingestion import DocumentIngestionService
    from app.services.rag_service import RAGService

    test_settings = Settings(
        chroma_path=tmp_path / "chroma",
        upload_dir=tmp_path / "uploads",
        bm25_index_path=tmp_path / "chroma" / "bm25_index.json",
        enable_hybrid_search=True,
        similarity_threshold=0.1,
    )

    fake_store = FakeVectorStore()
    monkeypatch.setattr(DocumentIngestionService, "_vector_store", lambda self: fake_store)
    monkeypatch.setattr(RAGService, "_vector_store", lambda self: fake_store)

    doc_path = tmp_path / "test_doc.txt"
    doc_path.write_text(
        "Project Orion protocol code is PX-9942. Security clearance level is Tier 5.",
        encoding="utf-8",
    )

    ingestion_service = DocumentIngestionService(test_settings)
    result = ingestion_service.ingest(doc_path, "test_doc.txt", owner_id="alice")
    assert result.chunks > 0

    # Ensure BM25 index file was written
    assert (tmp_path / "chroma" / "bm25_index.json").exists()

    # Query with exact alphanumeric code (which BM25 excels at)
    rag_service = RAGService(test_settings)
    chunks = rag_service._retrieve("PX-9942", user={"username": "alice", "role": "user"}, hybrid_search=True)
    assert len(chunks) >= 1
    assert "Project Orion" in chunks[0].document.page_content

