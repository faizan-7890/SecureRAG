"""Hybrid search engine for SecureRAG.

Combines dense vector retrieval (Chroma) and sparse keyword retrieval (Okapi BM25)
using Reciprocal Rank Fusion (RRF), with optional Multi-Query Expansion.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.models.schemas import Source

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.documents import Document
    from app.services.rag_service import RetrievedChunk


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    return re.findall(r"\b\w+\b", text.lower())


class BM25Index:
    """Lightweight in-memory and persistent Okapi BM25 sparse index."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_lengths: list[int] = []
        self.avgdl: float = 0.0
        self.doc_freqs: dict[str, int] = {}
        self.idf: dict[str, float] = {}

    @property
    def total_docs(self) -> int:
        return len(self.documents)

    def clear(self) -> None:
        """Clear the in-memory index."""
        self.documents.clear()
        self.doc_lengths.clear()
        self.avgdl = 0.0
        self.doc_freqs.clear()
        self.idf.clear()

    def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> None:
        """Add new documents to the BM25 index and recalculate statistics."""
        for i, doc in enumerate(documents):
            doc_id = ids[i] if ids and i < len(ids) else doc.metadata.get("chunk_id", f"doc_{len(self.documents)}")
            tokens = _tokenize(doc.page_content)
            self.documents.append(
                {
                    "id": doc_id,
                    "page_content": doc.page_content,
                    "metadata": dict(doc.metadata),
                    "tokens": tokens,
                }
            )
        self._recompute_stats()

    def _recompute_stats(self) -> None:
        """Recalculate average document length, term document frequencies, and IDF."""
        n_docs = len(self.documents)
        if n_docs == 0:
            self.doc_lengths = []
            self.avgdl = 0.0
            self.doc_freqs = {}
            self.idf = {}
            return

        self.doc_lengths = [len(doc["tokens"]) for doc in self.documents]
        self.avgdl = sum(self.doc_lengths) / n_docs

        # Calculate document frequencies
        doc_freqs: dict[str, int] = {}
        for doc in self.documents:
            unique_terms = set(doc["tokens"])
            for term in unique_terms:
                doc_freqs[term] = doc_freqs.get(term, 0) + 1

        self.doc_freqs = doc_freqs

        # Compute Robertson-Spärck Jones IDF
        idf: dict[str, float] = {}
        for term, freq in doc_freqs.items():
            idf[term] = math.log(1.0 + (n_docs - freq + 0.5) / (freq + 0.5))

        self.idf = idf

    def search(
        self,
        query: str,
        top_k: int = 10,
        user: dict[str, str] | None = None,
    ) -> list[tuple[Document, float]]:
        """Search the index with BM25 scoring and RBAC owner filtering."""
        from langchain_core.documents import Document

        if not self.documents:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores: list[tuple[int, float]] = []

        for idx, doc in enumerate(self.documents):
            # Check RBAC access
            metadata = doc["metadata"]
            if user and user.get("role") != "admin":
                owner_id = metadata.get("owner_id", "legacy")
                if owner_id not in {user.get("username"), "legacy"}:
                    continue

            # Calculate BM25 score
            doc_tokens = doc["tokens"]
            doc_len = len(doc_tokens)
            if doc_len == 0:
                continue

            # Compute term frequencies in this document
            term_counts: dict[str, int] = {}
            for token in doc_tokens:
                term_counts[token] = term_counts.get(token, 0) + 1

            score = 0.0
            for q_term in query_tokens:
                if q_term in term_counts:
                    tf = term_counts[q_term]
                    idf = self.idf.get(q_term, 0.0)
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
                    score += idf * (numerator / denominator)

            if score > 0.0:
                scores.append((idx, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        results: list[tuple[Document, float]] = []
        for idx, score in scores[:top_k]:
            raw_doc = self.documents[idx]
            doc_obj = Document(
                page_content=raw_doc["page_content"],
                metadata=raw_doc["metadata"],
            )
            results.append((doc_obj, score))

        return results

    def save(self, path: Path) -> None:
        """Persist BM25 index to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "documents": [
                {
                    "id": d["id"],
                    "page_content": d["page_content"],
                    "metadata": d["metadata"],
                }
                for d in self.documents
            ],
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        logger.debug("Saved BM25 index (%d documents) to %s", len(self.documents), path)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        """Load BM25 index from a JSON file."""
        index = cls()
        if not path.exists():
            return index

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            index.k1 = data.get("k1", 1.5)
            index.b = data.get("b", 0.75)
            for item in data.get("documents", []):
                tokens = _tokenize(item["page_content"])
                index.documents.append(
                    {
                        "id": item["id"],
                        "page_content": item["page_content"],
                        "metadata": item["metadata"],
                        "tokens": tokens,
                    }
                )
            index._recompute_stats()
            logger.info("Loaded BM25 index (%d documents) from %s", len(index.documents), path)
        except Exception as error:
            logger.warning("Failed to load BM25 index from %s: %s", path, error)
        return index

    def remove_document(self, document_id: str) -> int:
        """Remove all BM25 entries that belong to the given document_id.

        Returns the number of chunks removed.
        """
        before = len(self.documents)
        self.documents = [
            doc for doc in self.documents
            if doc.get("metadata", {}).get("document_id") != document_id
        ]
        removed = before - len(self.documents)
        if removed > 0:
            self._recompute_stats()
            logger.info("Removed %d BM25 entries for document %s", removed, document_id)
        return removed




def reciprocal_rank_fusion(
    dense_results: list[RetrievedChunk],
    sparse_results: list[tuple[Document, float]],
    rrf_k: int = 60,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> list[RetrievedChunk]:
    """Fuse dense vector retrieval and sparse BM25 results using Reciprocal Rank Fusion.

    Maintains calibrated relevance scores while ordering candidates by combined RRF rank.
    """
    from app.services.rag_service import RetrievedChunk

    fused_ranks: dict[str, float] = {}
    doc_map: dict[str, Document] = {}
    dense_scores: dict[str, float] = {}
    sparse_scores: dict[str, float] = {}

    def _doc_key(doc: Document) -> str:
        meta = getattr(doc, "metadata", {})
        return str(
            meta.get("chunk_id")
            or f"{meta.get('filename')}:{meta.get('chunk_index')}:{getattr(doc, 'page_content', '')[:100]}:{meta.get('owner_id')}"
        )

    # 1. Score dense candidates
    for rank, chunk in enumerate(dense_results, start=1):
        key = _doc_key(chunk.document)
        doc_map[key] = chunk.document
        dense_scores[key] = chunk.relevance_score
        dense_rrf = dense_weight / (rrf_k + rank)
        fused_ranks[key] = fused_ranks.get(key, 0.0) + dense_rrf

    # 2. Score sparse candidates
    max_sparse_score = max((s for _, s in sparse_results), default=1.0)
    for rank, (doc, score) in enumerate(sparse_results, start=1):
        key = _doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        sparse_scores[key] = score
        sparse_rrf = sparse_weight / (rrf_k + rank)
        fused_ranks[key] = fused_ranks.get(key, 0.0) + sparse_rrf

    if not fused_ranks:
        return []

    # Sort documents by combined RRF score descending
    sorted_items = sorted(fused_ranks.items(), key=lambda item: item[1], reverse=True)

    result_chunks: list[RetrievedChunk] = []
    for key, _ in sorted_items:
        doc = doc_map[key]
        if key in dense_scores and key in sparse_scores:
            # Matched in both dense and sparse: strong signal
            calibrated_score = min(1.0, dense_scores[key] + 0.05)
        elif key in dense_scores:
            calibrated_score = dense_scores[key]
        else:
            # Sparse-only match
            ratio = sparse_scores[key] / max(max_sparse_score, 0.001)
            calibrated_score = min(1.0, 0.5 + 0.45 * ratio)

        result_chunks.append(
            RetrievedChunk(
                document=doc,
                relevance_score=round(calibrated_score, 4),
            )
        )

    return result_chunks


class MultiQueryExpander:
    """Expands user questions into multiple query variations using an LLM."""

    @staticmethod
    def expand(question: str, settings: Settings, count: int = 3) -> list[str]:
        """Generate variations of the query. Always includes original query first."""
        api_key = settings.effective_api_key
        if not api_key or count <= 1:
            return [question]

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = settings.openai_model
        base_url = settings.openai_base_url

        if api_key.startswith("AIzaSy") or "gemini" in model.lower() or bool(settings.gemini_api_key):
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
            if model == "gpt-4o-mini" or not model.startswith("gemini"):
                model = "gemini-1.5-flash"

        kwargs: dict[str, object] = {
            "model": model,
            "api_key": api_key,
            "temperature": 0.2,
            "max_tokens": 256,
        }
        if base_url:
            kwargs["base_url"] = base_url

        try:
            llm = ChatOpenAI(**kwargs)
            response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            f"You are an AI assistant helping to improve search in a document database. "
                            f"Given a user question, generate {count} alternative search queries or sub-questions "
                            f"that capture different perspectives, synonyms, or specific key terms of the question. "
                            f"Return ONLY the questions, one per line, with no numbers, prefixes, or bullet points."
                        )
                    ),
                    HumanMessage(content=question),
                ]
            )
            content = response.content if isinstance(response.content, str) else str(response.content)
            lines = [line.strip().lstrip("0123456789.-* ") for line in content.splitlines() if line.strip()]
            queries = [question]
            for line in lines:
                if line and line.lower() != question.lower() and line not in queries:
                    queries.append(line)
            logger.info("Expanded query into %d variations: %s", len(queries), queries)
            return queries[: count + 1]
        except Exception as error:
            logger.warning("MultiQueryExpander failed: %s; falling back to original query", error)
            return [question]
