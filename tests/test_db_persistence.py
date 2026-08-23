"""Unit & Integration Tests for PostgreSQL / SQLAlchemy 2.0 and Redis Persistence Layer."""

import os
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import db_session, get_engine, init_db, reset_db_for_testing
from app.core.security import UserStore, authenticate, _verify_password
from app.core.session_store import SessionStore
from app.models.db_models import DocumentDB, UserDB
from app.services.ingestion import DocumentRegistry, IngestionResult


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Set up an isolated SQLite database for each test run."""
    db_file = tmp_path / "test_persistence.db"
    db_url = f"sqlite:///{db_file}"
    reset_db_for_testing(db_url)
    UserStore.users.clear()
    DocumentRegistry._records.clear()
    SessionStore.clear()
    yield
    reset_db_for_testing(db_url)


def test_user_db_crud_and_auth():
    # 1. Add User via UserStore
    UserStore.add("alice_test", "SecretPassword123!", "user")

    # 2. Verify direct SQL persistence
    with db_session() as session:
        user_row = session.scalar(select(UserDB).where(UserDB.username == "alice_test"))
        assert user_row is not None
        assert user_row.username == "alice_test"
        assert user_row.role == "user"
        assert _verify_password("SecretPassword123!", user_row.hashed_password)

    # 3. Retrieve and authenticate
    user_dict = UserStore.get("alice_test")
    assert user_dict is not None
    assert user_dict["username"] == "alice_test"

    settings = Settings(auth_secret="test-secret")
    auth_result = authenticate("alice_test", "SecretPassword123!", settings)
    assert auth_result is not None
    assert auth_result["username"] == "alice_test"

    bad_auth = authenticate("alice_test", "WrongPassword", settings)
    assert bad_auth is None

    # 4. Update Role
    assert UserStore.update_role("alice_test", "admin") is True
    with db_session() as session:
        user_row = session.scalar(select(UserDB).where(UserDB.username == "alice_test"))
        assert user_row is not None
        assert user_row.role == "admin"


def test_document_db_crud_and_rbac_listing():
    now_iso = datetime.now(timezone.utc).isoformat()
    result = IngestionResult(
        document_id="doc-12345",
        filename="security_handbook.pdf",
        chunks=8,
        uploaded_at=now_iso,
        owner_id="bob_admin",
        file_extension=".pdf",
        source_sha256="abcdef1234567890",
        source_size_bytes=4096,
    )

    # 1. Add Document via DocumentRegistry
    DocumentRegistry.add(result)

    # 2. Verify SQL persistence
    with db_session() as session:
        doc_row = session.scalar(select(DocumentDB).where(DocumentDB.document_id == "doc-12345"))
        assert doc_row is not None
        assert doc_row.filename == "security_handbook.pdf"
        assert doc_row.chunks_count == 8
        assert doc_row.owner_id == "bob_admin"

    # 3. Verify DocumentRegistry.get and all
    rec = DocumentRegistry.get("doc-12345")
    assert rec is not None
    assert rec.filename == "security_handbook.pdf"

    # Admin sees all
    all_docs_admin = DocumentRegistry.all(owner_id="charlie", role="admin", auth_enabled=True)
    assert len(all_docs_admin) >= 1

    # Another user does not see bob's doc
    all_docs_other = DocumentRegistry.all(owner_id="charlie", role="user", auth_enabled=True)
    assert len(all_docs_other) == 0

    # 4. Delete document
    assert DocumentRegistry.remove("doc-12345") is True
    with db_session() as session:
        doc_row = session.scalar(select(DocumentDB).where(DocumentDB.document_id == "doc-12345"))
        assert doc_row is None


def test_session_store_multi_turn_and_clear():
    session_id = "test-sess-xyz"
    SessionStore.clear(session_id)

    # Initially empty
    assert len(SessionStore.get_history(session_id)) == 0

    # Add turn
    SessionStore.add_turn(
        session_id=session_id,
        user_message="What is the travel policy?",
        assistant_message="The travel policy allows economy flights up to $500.",
        max_messages=10,
    )

    history = SessionStore.get_history(session_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "What is the travel policy?"
    assert history[1].role == "assistant"

    # Clear specific session
    SessionStore.clear(session_id)
    assert len(SessionStore.get_history(session_id)) == 0


def test_session_store_ttl_cleanup():
    session_id = "sess-expire"
    SessionStore.add_message(session_id, "user", "Hello")
    assert len(SessionStore.get_history(session_id)) == 1

    # Cleanup with 0 second TTL should purge
    removed = SessionStore.cleanup(ttl_seconds=-1)
    assert removed >= 1
    assert len(SessionStore.get_history(session_id)) == 0
