"""Semantic Response Cache for SecureRAG.

Caches query embeddings and high-confidence grounded LLM responses to provide
instant (<10ms) responses with 0 token consumption on identical or paraphrased queries.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.models.schemas import ChatResponse, Source

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(min(dot / (norm_a * norm_b), 1.0), -1.0)


@dataclass
class CacheEntry:
    query_text: str
    embedding: list[float]
    answer: str
    sources: list[dict[str, Any]]
    timestamp: float
    ttl_seconds: int

    def is_expired(self, current_time: float) -> bool:
        return (current_time - self.timestamp) > self.ttl_seconds


class SemanticCache:
    """Thread-safe in-memory and disk-backed semantic response cache."""

    _instance: SemanticCache | None = None
    _lock = threading.Lock()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.entries: list[CacheEntry] = []
        self._cache_lock = threading.Lock()
        self._persistence_path: Path = (
            settings.semantic_cache_path
            or (settings.upload_dir.parent / "cache" / "semantic_cache.json")
        )
        self._load_from_disk()

    @classmethod
    def get_instance(cls, settings: Settings) -> SemanticCache:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(settings)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear singleton for test isolation."""
        with cls._lock:
            if cls._instance:
                cls._instance.clear()
            cls._instance = None

    def clear(self) -> None:
        with self._cache_lock:
            self.entries.clear()
            if self._persistence_path.exists():
                try:
                    self._persistence_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _load_from_disk(self) -> None:
        if not self._persistence_path.exists():
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            loaded: list[CacheEntry] = []
            for item in data:
                entry = CacheEntry(
                    query_text=item["query_text"],
                    embedding=item["embedding"],
                    answer=item["answer"],
                    sources=item.get("sources", []),
                    timestamp=item["timestamp"],
                    ttl_seconds=item.get("ttl_seconds", self.settings.semantic_cache_ttl_seconds),
                )
                if not entry.is_expired(now):
                    loaded.append(entry)
            with self._cache_lock:
                self.entries = loaded
            logger.info("Loaded %d semantic cache entries from disk", len(loaded))
        except Exception as err:
            logger.warning("Could not load semantic cache from %s: %s", self._persistence_path, err)

    def _save_to_disk(self) -> None:
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_lock:
                raw_data = [asdict(e) for e in self.entries]
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2)
        except Exception as err:
            logger.warning("Could not save semantic cache to disk: %s", err)

    def lookup(
        self,
        query_text: str,
        query_embedding: list[float],
        threshold: float | None = None,
    ) -> ChatResponse | None:
        """Search for a semantically similar cached response."""
        if not self.settings.enable_semantic_cache:
            return None

        sim_threshold = threshold or self.settings.semantic_cache_threshold
        now = time.time()

        with self._cache_lock:
            # Filter expired entries
            valid_entries = [e for e in self.entries if not e.is_expired(now)]
            if len(valid_entries) != len(self.entries):
                self.entries = valid_entries

            best_entry: CacheEntry | None = None
            best_similarity = 0.0

            for entry in valid_entries:
                # Fast path: exact string match
                if entry.query_text.strip().lower() == query_text.strip().lower():
                    best_entry = entry
                    best_similarity = 1.0
                    break

                sim = _cosine_similarity(query_embedding, entry.embedding)
                if sim > best_similarity:
                    best_similarity = sim
                    best_entry = entry

            if best_entry and best_similarity >= sim_threshold:
                logger.info(
                    "Semantic cache HIT (similarity=%.4f >= %.4f) for query: '%s' -> matched '%s'",
                    best_similarity,
                    sim_threshold,
                    query_text,
                    best_entry.query_text,
                )
                sources = [Source(**s) for s in best_entry.sources]
                return ChatResponse(
                    answer=best_entry.answer,
                    sources=sources,
                    cached=True,
                )

        return None

    def store(
        self,
        query_text: str,
        query_embedding: list[float],
        answer: str,
        sources: list[Source],
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a new query-response pair in the semantic cache."""
        if not self.settings.enable_semantic_cache:
            return

        now = time.time()
        ttl = ttl_seconds or self.settings.semantic_cache_ttl_seconds
        sources_dict = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in sources]

        entry = CacheEntry(
            query_text=query_text,
            embedding=query_embedding,
            answer=answer,
            sources=sources_dict,
            timestamp=now,
            ttl_seconds=ttl,
        )

        with self._cache_lock:
            # Overwrite if exact match exists, otherwise append
            self.entries = [e for e in self.entries if e.query_text.strip().lower() != query_text.strip().lower()]
            self.entries.append(entry)

        self._save_to_disk()
        logger.debug("Stored query in semantic cache: '%s' (total cached=%d)", query_text, len(self.entries))
