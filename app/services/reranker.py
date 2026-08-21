"""Two-Stage Cross-Encoder Reranker for SecureRAG.

Computes deep cross-attention scores across (query, passage) pairs to rerank
candidates retrieved by Hybrid (Dense + BM25 RRF) search.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from app.core.config import Settings

if TYPE_CHECKING:
    from app.services.rag_service import RetrievedChunk

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Safely apply sigmoid to scale raw logits to [0.0, 1.0]."""
    return 1.0 / (1.0 + math.exp(-max(min(x, 20.0), -20.0)))


class CrossEncoderReranker:
    """Two-stage cross-encoder reranker for scoring query-passage relevance."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    @property
    def model(self):
        if not self.settings.enable_reranker:
            return None
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                logger.info("Initializing CrossEncoder model: %s", self.settings.reranker_model)
                self._model = CrossEncoder(
                    self.settings.reranker_model,
                    device="cpu",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to initialize CrossEncoder (%s), using fallback scoring: %s",
                    self.settings.reranker_model,
                    exc,
                )
                self._model = False
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Rerank candidates using cross-attention and return top_k chunks."""
        if not candidates:
            return []

        limit = top_k or self.settings.reranker_top_k or self.settings.top_k
        if len(candidates) <= 1:
            return candidates[:limit]

        from app.services.rag_service import RetrievedChunk

        model = self.model
        if not model:
            return sorted(candidates, key=lambda c: c.relevance_score, reverse=True)[:limit]

        try:
            pairs = [[query, chunk.document.page_content] for chunk in candidates]
            scores = model.predict(pairs)

            reranked: list[RetrievedChunk] = []
            for idx, raw_score in enumerate(scores):
                norm_score = _sigmoid(float(raw_score)) if isinstance(raw_score, (int, float)) else float(raw_score)
                norm_score = round(float(norm_score), 4)
                reranked.append(RetrievedChunk(document=candidates[idx].document, relevance_score=norm_score))

            reranked.sort(key=lambda c: c.relevance_score, reverse=True)
            logger.debug(
                "Reranked %d candidates to top %d (highest score=%.4f)",
                len(candidates),
                min(limit, len(reranked)),
                reranked[0].relevance_score if reranked else 0.0,
            )
            return reranked[:limit]
        except Exception as error:
            logger.warning("Cross-encoder reranking failed, falling back to candidate order: %s", error)
            return sorted(candidates, key=lambda c: c.relevance_score, reverse=True)[:limit]
