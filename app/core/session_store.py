"""Session store for conversational multi-turn chat history with Redis support and automated TTL."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import ClassVar

from app.core.config import get_settings
from app.models.schemas import ChatMessage

logger = logging.getLogger(__name__)


class SessionStore:
    """Multi-turn session history store supporting Redis with in-memory fallback and TTL expiration."""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _sessions: ClassVar[dict[str, list[ChatMessage]]] = {}
    _last_accessed: ClassVar[dict[str, float]] = {}
    _redis_client = None
    _redis_checked: ClassVar[bool] = False

    @classmethod
    def _get_redis(cls):
        """Lazy-initialize Redis client if configured."""
        if not cls._redis_checked:
            cls._redis_checked = True
            settings = get_settings()
            if settings.redis_url:
                try:
                    import redis

                    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
                    client.ping()
                    cls._redis_client = client
                    logger.info("Connected to Redis for session history storage (%s)", settings.redis_url.split("@")[-1])
                except Exception as err:
                    logger.warning("Redis connection failed (%s), falling back to in-memory store: %s", settings.redis_url, err)
                    cls._redis_client = None
        return cls._redis_client

    @classmethod
    def get_history(cls, session_id: str, max_messages: int = 10) -> list[ChatMessage]:
        """Retrieve recent conversation history for a session."""
        r = cls._get_redis()
        if r:
            try:
                settings = get_settings()
                key = f"securerag:session:{session_id}"
                raw_items = r.lrange(key, -max_messages, -1)
                r.expire(key, settings.session_ttl_seconds)
                return [ChatMessage(**json.loads(item)) for item in raw_items]
            except Exception as err:
                logger.warning("Redis lrange failed, falling back to memory: %s", err)

        with cls._lock:
            if session_id not in cls._sessions:
                return []
            cls._last_accessed[session_id] = time.time()
            return list(cls._sessions[session_id][-max_messages:])

    @classmethod
    def add_message(cls, session_id: str, role: str, content: str, max_messages: int = 10) -> None:
        """Append a single message to a session with TTL refresh."""
        msg = ChatMessage(role=role, content=content)
        r = cls._get_redis()
        if r:
            try:
                settings = get_settings()
                key = f"securerag:session:{session_id}"
                r.rpush(key, json.dumps({"role": role, "content": content}))
                r.ltrim(key, -max_messages, -1)
                r.expire(key, settings.session_ttl_seconds)
            except Exception as err:
                logger.warning("Redis rpush failed: %s", err)

        with cls._lock:
            if session_id not in cls._sessions:
                cls._sessions[session_id] = []
            cls._sessions[session_id].append(msg)
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
        cls.add_message(session_id, "user", user_message, max_messages=max_messages)
        cls.add_message(session_id, "assistant", assistant_message, max_messages=max_messages)

    @classmethod
    def clear(cls, session_id: str | None = None) -> None:
        """Clear history for a specific session or all sessions."""
        r = cls._get_redis()
        if r:
            try:
                if session_id is None:
                    keys = r.keys("securerag:session:*")
                    if keys:
                        r.delete(*keys)
                else:
                    r.delete(f"securerag:session:{session_id}")
            except Exception as err:
                logger.warning("Redis delete failed: %s", err)

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
