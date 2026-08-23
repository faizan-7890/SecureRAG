from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pypdf import PdfReader

from app.core.config import Settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


class UnsupportedDocumentError(ValueError):
    """Raised when an upload is not a document type supported by Milestone 1."""


class EmptyDocumentError(ValueError):
    """Raised when no extractable text is found in an uploaded document."""


@dataclass(frozen=True)
class IngestionResult:
    filename: str
    chunks: int
    document_id: str
    uploaded_at: str
    owner_id: str
    file_extension: str
    source_sha256: str
    source_size_bytes: int


class DocumentRegistry:
    """Registry of ingested documents with SQLAlchemy persistence and in-memory caching."""

    _records: dict[str, "DocumentRecord"] = {}

    @classmethod
    def add(cls, result: "IngestionResult") -> None:
        from app.models.schemas import DocumentRecord

        record = DocumentRecord(
            document_id=result.document_id,
            filename=result.filename,
            chunks=result.chunks,
            uploaded_at=result.uploaded_at,
            owner_id=result.owner_id,
            file_extension=result.file_extension,
            source_sha256=result.source_sha256,
            source_size_bytes=result.source_size_bytes,
        )
        cls._records[result.document_id] = record

        try:
            from datetime import datetime, timezone
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import DocumentDB

            with db_session() as session:
                existing = session.scalar(select(DocumentDB).where(DocumentDB.document_id == result.document_id))
                dt = datetime.fromisoformat(result.uploaded_at) if result.uploaded_at else datetime.now(timezone.utc)
                if existing:
                    existing.filename = result.filename
                    existing.chunks_count = result.chunks
                    existing.uploaded_at = dt
                    existing.owner_id = result.owner_id
                    existing.file_extension = result.file_extension
                    existing.source_sha256 = result.source_sha256
                    existing.source_size_bytes = result.source_size_bytes
                else:
                    doc_db = DocumentDB(
                        document_id=result.document_id,
                        filename=result.filename,
                        chunks_count=result.chunks,
                        uploaded_at=dt,
                        owner_id=result.owner_id,
                        file_extension=result.file_extension,
                        source_sha256=result.source_sha256,
                        source_size_bytes=result.source_size_bytes,
                    )
                    session.add(doc_db)
        except Exception:
            pass

    @classmethod
    def get(cls, document_id: str) -> "DocumentRecord | None":
        from app.models.schemas import DocumentRecord

        if document_id in cls._records:
            return cls._records[document_id]

        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import DocumentDB

            with db_session() as session:
                doc_db = session.scalar(select(DocumentDB).where(DocumentDB.document_id == document_id))
                if doc_db:
                    rec = DocumentRecord(
                        document_id=doc_db.document_id,
                        filename=doc_db.filename,
                        chunks=doc_db.chunks_count,
                        uploaded_at=doc_db.uploaded_at.isoformat() if hasattr(doc_db.uploaded_at, "isoformat") else str(doc_db.uploaded_at),
                        owner_id=doc_db.owner_id,
                        file_extension=doc_db.file_extension,
                        source_sha256=doc_db.source_sha256,
                        source_size_bytes=doc_db.source_size_bytes,
                    )
                    cls._records[document_id] = rec
                    return rec
        except Exception:
            pass

        return None

    @classmethod
    def all(
        cls,
        owner_id: str | None = None,
        role: str | None = None,
        auth_enabled: bool = False,
    ) -> list["DocumentRecord"]:
        """Return all records visible to the given caller."""
        from app.models.schemas import DocumentRecord

        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import DocumentDB

            with db_session() as session:
                docs_db = session.scalars(select(DocumentDB)).all()
                if docs_db:
                    for doc_db in docs_db:
                        if doc_db.document_id not in cls._records:
                            cls._records[doc_db.document_id] = DocumentRecord(
                                document_id=doc_db.document_id,
                                filename=doc_db.filename,
                                chunks=doc_db.chunks_count,
                                uploaded_at=doc_db.uploaded_at.isoformat() if hasattr(doc_db.uploaded_at, "isoformat") else str(doc_db.uploaded_at),
                                owner_id=doc_db.owner_id,
                                file_extension=doc_db.file_extension,
                                source_sha256=doc_db.source_sha256,
                                source_size_bytes=doc_db.source_size_bytes,
                            )
        except Exception:
            pass

        records = list(cls._records.values())
        if role == "admin" or (not auth_enabled and owner_id is None):
            return records
        if owner_id:
            return [r for r in records if r.owner_id in {owner_id, "legacy"}]
        return [r for r in records if r.owner_id == "legacy"]

    @classmethod
    def remove(cls, document_id: str) -> bool:
        """Remove a record from the registry and database. Returns True if it existed."""
        existed = cls._records.pop(document_id, None) is not None
        try:
            from sqlalchemy import select
            from app.core.db import db_session
            from app.models.db_models import DocumentDB

            with db_session() as session:
                doc_db = session.scalar(select(DocumentDB).where(DocumentDB.document_id == document_id))
                if doc_db:
                    session.delete(doc_db)
                    existed = True
        except Exception:
            pass

        return existed

class DocumentIngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embeddings: HuggingFaceEmbeddings | None = None

    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def _vector_store(self) -> Chroma:
        from langchain_chroma import Chroma

        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=self.settings.chroma_collection,
            persist_directory=str(self.settings.chroma_path),
            embedding_function=self.embeddings,
        )

    def ingest(self, file_path: Path, original_filename: str, owner_id: str | None = None) -> IngestionResult:
        start = time.perf_counter()
        extension = Path(original_filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise UnsupportedDocumentError(f"Unsupported file type. Use one of: {supported}.")

        documents = self._load_documents(file_path, original_filename, extension)
        if not documents:
            raise EmptyDocumentError("No readable text was found in this document.")

        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n# ", "\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
            keep_separator="start",
            add_start_index=True,
        )
        chunks = splitter.split_documents(documents)
        if not chunks:
            raise EmptyDocumentError("No text chunks could be created from this document.")

        document_id = str(uuid4())
        uploaded_at = datetime.now(UTC).isoformat()
        source_sha256 = self._sha256(file_path)
        source_size_bytes = file_path.stat().st_size
        ids: list[str] = []
        for index, chunk in enumerate(chunks):
            chunk_id = f"{document_id}:{index}"
            chunk.metadata.update(
                {
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "filename": original_filename,
                    "file_extension": extension,
                    "uploaded_at": uploaded_at,
                    "source_sha256": source_sha256,
                    "source_size_bytes": source_size_bytes,
                    "allowed_roles": "admin,user",
                    "owner_id": owner_id or "legacy",
                }
            )
            ids.append(chunk_id)

        self._vector_store().add_documents(chunks, ids=ids)

        # Update BM25 sparse index
        bm25_path = self.settings.bm25_index_path or (self.settings.chroma_path / "bm25_index.json")
        from app.services.hybrid_search import BM25Index
        bm25 = BM25Index.load(bm25_path)
        bm25.add_documents(chunks, ids=ids)
        bm25.save(bm25_path)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "Ingested %s: %d chunks in %.1fms",
            original_filename,
            len(chunks),
            duration_ms,
            extra={
                "doc_filename": original_filename,
                "chunks": len(chunks),
                "document_id": document_id,
                "duration_ms": duration_ms,
            },
        )
        result = IngestionResult(
            filename=original_filename,
            chunks=len(chunks),
            document_id=document_id,
            uploaded_at=uploaded_at,
            owner_id=owner_id or "legacy",
            file_extension=extension,
            source_sha256=source_sha256,
            source_size_bytes=source_size_bytes,
        )
        DocumentRegistry.add(result)
        return result


    def _load_documents(
        self, file_path: Path, filename: str, extension: str
    ) -> list[Document]:
        if extension == ".pdf":
            return self._load_pdf(file_path, filename)

        from langchain_core.documents import Document

        text = file_path.read_text(encoding="utf-8", errors="replace")
        text = self._normalise_text(text)
        if not text:
            return []
        return [Document(page_content=text, metadata={"filename": filename})]

    @staticmethod
    def _load_pdf(file_path: Path, filename: str) -> list[Document]:
        from langchain_core.documents import Document

        reader = PdfReader(str(file_path))
        pages: list[Document] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = DocumentIngestionService._normalise_text(page.extract_text() or "")
            if text:
                pages.append(
                    Document(
                        page_content=text,
                        metadata={"filename": filename, "page": page_number},
                    )
                )
        return pages

    @staticmethod
    def _normalise_text(text: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
