"""SQLAlchemy 2.0 Declarative Database Models for SecureRAG.

Defines the relational schema for User authentication/RBAC and Document metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


class UserDB(Base):
    """User account entity with password hash and RBAC role."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentDB(Base):
    """Document registry entity tracking ingested files and RBAC ownership."""

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(String(100), index=True, default="legacy", nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
