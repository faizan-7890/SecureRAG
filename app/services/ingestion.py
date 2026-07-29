from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pypdf import PdfReader

from app.core.config import Settings

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

    def ingest(self, file_path: Path, original_filename: str) -> IngestionResult:
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
                }
            )
            ids.append(chunk_id)

        self._vector_store().add_documents(chunks, ids=ids)
        return IngestionResult(filename=original_filename, chunks=len(chunks))

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
