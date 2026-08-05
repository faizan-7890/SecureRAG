from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.core.config import Settings
from app.core.session_store import SessionStore
from app.main import app
from app.models.schemas import (
    ChatMessage,
    StreamDoneEvent,
    StreamErrorEvent,
    StreamSourceEvent,
    StreamTokenEvent,
)
from app.services.rag_service import RAGService, RetrievedChunk


def test_session_store_basic_operations():
    SessionStore.clear()
    session_id = "test-session-1"

    # Empty history
    assert SessionStore.get_history(session_id) == []

    # Add single message
    SessionStore.add_message(session_id, "user", "Hello", max_messages=5)
    hist = SessionStore.get_history(session_id)
    assert len(hist) == 1
    assert hist[0].role == "user"
    assert hist[0].content == "Hello"

    # Add turn
    SessionStore.add_turn(session_id, "How are you?", "I am doing well.", max_messages=5)
    hist2 = SessionStore.get_history(session_id)
    assert len(hist2) == 3
    assert hist2[1].role == "user"
    assert hist2[2].role == "assistant"

    # Truncation with max_messages
    for i in range(10):
        SessionStore.add_message(session_id, "user", f"Msg {i}", max_messages=4)
    hist3 = SessionStore.get_history(session_id, max_messages=4)
    assert len(hist3) == 4
    assert hist3[-1].content == "Msg 9"

    # Clear specific session
    SessionStore.clear(session_id)
    assert SessionStore.get_history(session_id) == []


def test_session_store_cleanup_ttl():
    SessionStore.clear()
    SessionStore.add_message("old-session", "user", "old")
    # artificially age the session
    SessionStore._last_accessed["old-session"] = 1000.0

    SessionStore.add_message("new-session", "user", "new")

    removed = SessionStore.cleanup(ttl_seconds=3600)
    assert removed == 1
    assert SessionStore.get_history("old-session") == []
    assert len(SessionStore.get_history("new-session")) == 1
    SessionStore.clear()


def test_recontextualize_query_no_history():
    settings = Settings(openai_api_key="test-key", enable_query_recontextualization=True)
    service = RAGService(settings)

    result = service._recontextualize_query("What is the leave policy?", history=[])
    assert result == "What is the leave policy?"


def test_recontextualize_query_with_history():
    settings = Settings(openai_api_key="test-key", enable_query_recontextualization=True)
    service = RAGService(settings)

    history = [
        ChatMessage(role="user", content="Tell me about parental leave."),
        ChatMessage(role="assistant", content="Parental leave provides 16 weeks for primary caregivers."),
    ]

    mock_response = MagicMock()
    mock_response.content = "What are the rules for secondary caregivers under parental leave?"

    with patch("langchain_openai.ChatOpenAI.invoke", return_value=mock_response):
        standalone = service._recontextualize_query("What about secondary caregivers?", history=history)
        assert standalone == "What are the rules for secondary caregivers under parental leave?"


def test_recontextualize_query_fallback_on_error():
    settings = Settings(openai_api_key="test-key", enable_query_recontextualization=True)
    service = RAGService(settings)

    history = [ChatMessage(role="user", content="Hello")]

    with patch("langchain_openai.ChatOpenAI.invoke", side_effect=Exception("API connection error")):
        standalone = service._recontextualize_query("What is the leave policy?", history=history)
        assert standalone == "What is the leave policy?"


def test_answer_stream_without_api_key():
    settings = Settings(openai_api_key=None)
    service = RAGService(settings)

    events = list(service.answer_stream(question="Hello"))
    assert len(events) == 1
    assert isinstance(events[0], StreamErrorEvent)
    assert "API key is not configured" in events[0].error


def test_answer_stream_no_matching_chunks():
    settings = Settings(openai_api_key="test-key", enable_hybrid_search=False)
    service = RAGService(settings)

    with patch.object(service, "_retrieve", return_value=[]):
        events = list(service.answer_stream(question="Random non-existent topic"))

        assert len(events) == 3
        assert isinstance(events[0], StreamSourceEvent)
        assert events[0].sources == []
        assert isinstance(events[1], StreamTokenEvent)
        assert "could not find sufficiently relevant information" in events[1].token
        assert isinstance(events[2], StreamDoneEvent)
        assert events[2].done is True


def test_answer_stream_with_tokens():
    settings = Settings(openai_api_key="test-key", enable_hybrid_search=False)
    service = RAGService(settings)

    mock_doc = Document(
        page_content="Annual leave is 20 working days.",
        metadata={"filename": "policy.pdf", "page": 1, "chunk_index": 0, "owner_id": "test"},
    )
    mock_chunk = RetrievedChunk(document=mock_doc, relevance_score=0.9)

    mock_token_1 = MagicMock(content="Annual ")
    mock_token_2 = MagicMock(content="leave is 20 days.")

    with patch.object(service, "_retrieve", return_value=[mock_chunk]):
        with patch("langchain_openai.ChatOpenAI.stream", return_value=[mock_token_1, mock_token_2]):
            events = list(service.answer_stream(question="How much annual leave?", session_id="s1"))

            assert isinstance(events[0], StreamSourceEvent)
            assert len(events[0].sources) == 1
            assert events[0].sources[0].filename == "policy.pdf"

            assert isinstance(events[1], StreamTokenEvent)
            assert events[1].token == "Annual "

            assert isinstance(events[2], StreamTokenEvent)
            assert events[2].token == "leave is 20 days."

            assert isinstance(events[3], StreamDoneEvent)
            assert events[3].done is True
            assert events[3].total_tokens == 2
            assert events[3].session_id == "s1"


def test_api_chat_stream_endpoint():
    client = TestClient(app)

    mock_doc = Document(
        page_content="Sick leave provides 10 days.",
        metadata={"filename": "sick_leave.pdf", "page": 2, "chunk_index": 1, "owner_id": "legacy"},
    )
    mock_chunk = RetrievedChunk(document=mock_doc, relevance_score=0.88)

    mock_token_1 = MagicMock(content="You get 10 ")
    mock_token_2 = MagicMock(content="sick days.")
    settings = Settings(openai_api_key="mock-test-key", enable_hybrid_search=False)

    with patch("app.api.chat.get_settings", return_value=settings):
        with patch("app.services.rag_service.RAGService._retrieve", return_value=[mock_chunk]):
            with patch("langchain_openai.ChatOpenAI.stream", return_value=[mock_token_1, mock_token_2]):
                response = client.post(
                    "/chat/stream",
                    json={
                        "question": "What is sick leave?",
                        "session_id": "sess-stream-1",
                        "hybrid_search": False,
                    },
                )
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

                content = response.text
                assert "event: sources" in content
                assert "sick_leave.pdf" in content
                assert "event: token" in content
                assert "You get 10 " in content
                assert "event: done" in content


def test_api_chat_with_history():
    client = TestClient(app)

    mock_doc = Document(
        page_content="Employees receive 20 days of annual leave.",
        metadata={"filename": "policy.pdf", "page": 1, "chunk_index": 0, "owner_id": "legacy"},
    )
    mock_chunk = RetrievedChunk(document=mock_doc, relevance_score=0.92)
    mock_response = MagicMock(content="You receive 20 annual days.")
    settings = Settings(openai_api_key="mock-test-key", enable_hybrid_search=False)

    with patch("app.api.chat.get_settings", return_value=settings):
        with patch("app.services.rag_service.RAGService._retrieve", return_value=[mock_chunk]):
            with patch("langchain_openai.ChatOpenAI.invoke", return_value=mock_response):
                response = client.post(
                    "/chat",
                    json={
                        "question": "How much leave?",
                        "history": [{"role": "user", "content": "Hi"}],
                        "session_id": "sess-chat-1",
                        "hybrid_search": False,
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["answer"] == "You receive 20 annual days."
                assert len(data["sources"]) == 1
                assert data["session_id"] == "sess-chat-1"
