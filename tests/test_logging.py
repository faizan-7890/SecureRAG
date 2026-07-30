"""Tests for the structured logging infrastructure."""

import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JSONFormatter, setup_logging
from app.main import app


def test_json_formatter_produces_valid_json():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "Hello world"
    assert "timestamp" in parsed


def test_json_formatter_includes_exception():
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=1,
        msg="fail", args=(), exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "boom" in parsed["exception"]


def test_setup_logging_configures_root_logger():
    setup_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(h.formatter, JSONFormatter) for h in root.handlers)


def test_setup_logging_is_idempotent():
    setup_logging("INFO")
    handler_count_before = len(logging.getLogger().handlers)
    setup_logging("INFO")
    handler_count_after = len(logging.getLogger().handlers)
    assert handler_count_after == handler_count_before


def test_request_id_header_is_set():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) == 12
