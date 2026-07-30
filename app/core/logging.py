"""Structured JSON logging for SecureRAG.

Provides a JSON formatter and a context-variable-based request-ID
so that every log line emitted during a request can be correlated.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Context variable set by the request middleware and read by the formatter.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach the request ID when available.
        rid = request_id_ctx.get()
        if rid:
            log_entry["request_id"] = rid

        # Include exception info when present.
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Merge any *extra* keys the caller passed via `logger.info("…", extra={…})`.
        for key in ("extra", "duration_ms", "status_code", "method", "path",
                     "doc_filename", "chunks", "document_id", "username", "question"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with the JSON formatter.

    Call this once at application startup (before any log statements).
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Prevent duplicate handlers when `uvicorn --reload` re-imports.
    if any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter)
           for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers.
    for noisy in ("httpcore", "httpx", "chromadb", "sentence_transformers",
                  "uvicorn.access", "urllib3", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
