"""In-memory session store for conversational multi-turn chat history."""

from __future__ import annotations

import logging
import threading
import time
from typing import ClassVar

from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe in-memory store for conversational chat history."""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _sessions: ClassVar[dict[str, list[ChatMessage]]] = {}
    _last_accessed: ClassVar[dict[str, float]] = {}

    @classmethod
    def get_history(cls, session_id: str, max_messages: int = 10) -> list[ChatMessage]:
        """Retrieve recent conversation history for a session."""
        with cls._lock:
            if session_id not in cls._sessions:
                return []
            cls._last_accessed[session_id] = time.time()
            return list(cls._sessions[session_id][-max_messages:])

    @classmethod
    def add_message(cls, session_id: str, role: str, content: str, max_messages: int = 10) -> None:
        """Append a single message to a session."""
        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = []
            cls._sessions[session_id].append(ChatMessage(role=role, content=content))
            if len(cls._sessions[session_id]) > max_messages:
                cls._sessions[session_id] = cls._sessions[session_id][-max_messages:]
            cls._last_accessed[session_id] = time.time()

    @classmethod
    def add_turn(
        cls,
        session_id: str,
        user_message: str,
        assistant_message: str,
        max_messages: int = 10,
    ) -> None:
        """Add both user question and assistant answer in a single turn."""
        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = []
            cls._sessions[session_id].append(ChatMessage(role="user", content=user_message))
            cls._sessions[session_id].append(ChatMessage(role="assistant", content=assistant_message))
            if len(cls._sessions[session_id]) > max_messages:
                cls._sessions[session_id] = cls._sessions[session_id][-max_messages:]
            cls._last_accessed[session_id] = time.time()

    @classmethod
    def clear(cls, session_id: str | None = None) -> None:
        """Clear history for a specific session or all sessions."""
        with cls._lock:
            if session_id is None:
                cls._sessions.clear()
                cls._last_accessed.clear()
            else:
                cls._sessions.pop(session_id, None)
                cls._last_accessed.pop(session_id, None)

    @classmethod
    def cleanup(cls, ttl_seconds: int = 3600) -> int:
        """Purge sessions that have been inactive longer than ttl_seconds."""
        now = time.time()
        removed = 0
        with cls._lock:
            expired = [
                s_id
                for s_id, last_ts in cls._last_accessed.items()
                if (now - last_ts) > ttl_seconds
            ]
            for s_id in expired:
                cls._sessions.pop(s_id, None)
                cls._last_accessed.pop(s_id, None)
                removed += 1
        if removed:
            logger.info("Cleaned up %d expired chat sessions", removed)
        return removed
