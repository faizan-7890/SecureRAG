"""Tests for Two-Stage Cross-Encoder Reranker and Semantic Response Cache."""

import time
import pytest
from langchain_core.documents import Document

from app.core.config import Settings
from app.models.schemas import Source
from app.services.rag_service import RetrievedChunk
from app.services.reranker import CrossEncoderReranker
from app.services.semantic_cache import CacheEntry, SemanticCache, _cosine_similarity


def test_cosine_similarity_edge_cases():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cross_encoder_reranker_sorting(monkeypatch, tmp_path):
    settings = Settings(
        enable_reranker=True,
        reranker_top_k=2,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    reranker = CrossEncoderReranker(settings)

    # Mock CrossEncoder predict
    class FakeModel:
        def predict(self, pairs):
            # return custom scores: chunk 1 is most relevant, chunk 0 is medium, chunk 2 is low
            scores = []
            for query, text in pairs:
                if "vacation" in text:
                    scores.append(2.5)  # highest
                elif "holiday" in text:
                    scores.append(0.5)  # medium
                else:
                    scores.append(-2.0)  # lowest
            return scores

    monkeypatch.setattr(reranker, "_model", FakeModel())

    candidates = [
        RetrievedChunk(document=Document(page_content="Company holiday rules", metadata={"chunk_index": 0}), relevance_score=0.4),
        RetrievedChunk(document=Document(page_content="Paid vacation leave policy", metadata={"chunk_index": 1}), relevance_score=0.5),
        RetrievedChunk(document=Document(page_content="Unrelated equipment guidance", metadata={"chunk_index": 2}), relevance_score=0.6),
    ]

    reranked = reranker.rerank("How many vacation days?", candidates, top_k=2)
    assert len(reranked) == 2
    assert "vacation" in reranked[0].document.page_content
    assert "holiday" in reranked[1].document.page_content
    assert reranked[0].relevance_score > reranked[1].relevance_score


def test_cross_encoder_fallback_when_disabled(tmp_path):
    settings = Settings(
        enable_reranker=False,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    reranker = CrossEncoderReranker(settings)
    candidates = [
        RetrievedChunk(document=Document(page_content="Text A"), relevance_score=0.8),
        RetrievedChunk(document=Document(page_content="Text B"), relevance_score=0.9),
    ]
    # When model is None/disabled, preserves candidate sorted order
    reranked = reranker.rerank("query", candidates, top_k=2)
    assert reranked[0].relevance_score == 0.9


def test_semantic_cache_store_and_hit(tmp_path):
    cache_path = tmp_path / "cache" / "test_cache.json"
    settings = Settings(
        enable_semantic_cache=True,
        semantic_cache_threshold=0.95,
        semantic_cache_path=cache_path,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    SemanticCache.reset()
    cache = SemanticCache.get_instance(settings)
    cache.clear()

    query_emb = [0.1] * 384
    sources = [Source(filename="policy.pdf", excerpt="20 days leave", page=1, chunk_index=0, relevance_score=0.9)]

    # 1. Miss initially
    miss = cache.lookup("How many leave days?", query_emb)
    assert miss is None

    # 2. Store
    cache.store("How many leave days?", query_emb, "20 days annual leave.", sources)

    # 3. Exact query hit
    hit = cache.lookup("How many leave days?", query_emb)
    assert hit is not None
    assert hit.cached is True
    assert hit.answer == "20 days annual leave."
    assert len(hit.sources) == 1
    assert hit.sources[0].filename == "policy.pdf"

    # 4. Near-identical semantic vector hit (cosine similarity ~ 0.999)
    similar_emb = [0.1001] * 384
    near_hit = cache.lookup("How much annual leave do I get?", similar_emb)
    assert near_hit is not None
    assert near_hit.cached is True
    assert near_hit.answer == "20 days annual leave."

    # 5. Dissimilar vector miss
    dissimilar_emb = [-0.1] * 384
    dissimilar_miss = cache.lookup("What is expense meal limit?", dissimilar_emb)
    assert dissimilar_miss is None


def test_semantic_cache_ttl_expiration(tmp_path):
    settings = Settings(
        enable_semantic_cache=True,
        semantic_cache_ttl_seconds=1,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    SemanticCache.reset()
    cache = SemanticCache.get_instance(settings)
    cache.clear()

    query_emb = [0.2] * 384
    cache.store("Query", query_emb, "Answer", [], ttl_seconds=1)

    # Immediately should hit
    assert cache.lookup("Query", query_emb) is not None

    # Wait for expiry
    time.sleep(1.1)
    assert cache.lookup("Query", query_emb) is None


def test_semantic_cache_disabled_flag(tmp_path):
    settings = Settings(
        enable_semantic_cache=False,
        upload_dir=tmp_path / "uploads",
        chroma_path=tmp_path / "chroma",
    )
    SemanticCache.reset()
    cache = SemanticCache.get_instance(settings)

    cache.store("Query", [0.1] * 384, "Answer", [])
    assert cache.lookup("Query", [0.1] * 384) is None
