"""Database Engine & Session Management for SecureRAG.

Supports PostgreSQL in production and automated zero-config SQLite fallback for local development.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.db_models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    """Initialize or retrieve the SQLAlchemy database engine."""
    global _engine, _SessionFactory
    if _engine is None or database_url is not None:
        settings = get_settings()
        url = database_url or settings.database_url

        # Ensure sqlite parent directory exists
        if url.startswith("sqlite"):
            db_path_str = url.replace("sqlite:///", "")
            if db_path_str and not db_path_str.startswith(":memory:"):
                db_path = Path(db_path_str)
                db_path.parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False}
        else:
            connect_args = {}

        _engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            echo=False,
        )
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("Initialized database engine with URL: %s", url.split("@")[-1] if "@" in url else url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Retrieve the active Session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


def init_db(database_url: str | None = None) -> None:
    """Initialize and create all database tables if they do not already exist."""
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized and verified.")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed database session."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for programmatic database transactions in background services."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_db_for_testing(database_url: str | None = None) -> None:
    """Drop and recreate all tables (used exclusively for test isolation)."""
    global _engine, _SessionFactory
    _engine = None
    _SessionFactory = None
    engine = get_engine(database_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
