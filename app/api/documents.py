from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.core.security import current_user, require_current_user
from app.models.schemas import ChunkDetail, DocumentChunksResponse, DocumentListResponse, UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> UploadResponse:
    from app.services.ingestion import (
        DocumentIngestionService,
        EmptyDocumentError,
        UnsupportedDocumentError,
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")
    original_filename = Path(file.filename).name
    extension = Path(original_filename).suffix.lower()
    if extension not in {".pdf", ".txt", ".md", ".markdown"}:
        logger.warning("Upload rejected: unsupported type %s", extension, extra={"doc_filename": original_filename})
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and Markdown files are supported.")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.upload_dir / f"{uuid4()}{extension}"
    content = await file.read()
    if not content:
        logger.warning("Upload rejected: empty file %s", original_filename, extra={"doc_filename": original_filename})
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    stored_path.write_bytes(content)

    logger.info("Processing upload: %s (%d bytes)", original_filename, len(content), extra={"doc_filename": original_filename})

    try:
        result = DocumentIngestionService(settings).ingest(stored_path, original_filename, user["username"] if user else None)
    except (UnsupportedDocumentError, EmptyDocumentError) as error:
        stored_path.unlink(missing_ok=True)
        logger.warning("Ingestion failed for %s: %s", original_filename, error, extra={"doc_filename": original_filename})
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected ingestion error for %s", original_filename)
        raise HTTPException(status_code=500, detail="Document ingestion failed.") from error

    logger.info(
        "Upload complete: %s → %d chunks (document_id=%s)",
        result.filename, result.chunks, result.document_id,
        extra={"doc_filename": result.filename, "chunks": result.chunks, "document_id": result.document_id},
    )
    return UploadResponse(
        message="Document ingested",
        filename=result.filename,
        chunks=result.chunks,
        document_id=result.document_id,
        owner_id=result.owner_id,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> DocumentListResponse:
    """List all ingested documents visible to the authenticated caller.

    - Admins see every document.
    - Regular users see only their own documents and 'legacy' (unauthenticated) uploads.
    - Unauthenticated callers see only 'legacy' documents when auth is enabled, or all documents if auth is not configured.
    """
    from app.services.ingestion import DocumentRegistry

    owner_id = user.get("username") if user else None
    role = user.get("role") if user else None
    auth_enabled = bool(settings and settings.auth_secret)
    records = DocumentRegistry.all(owner_id=owner_id, role=role, auth_enabled=auth_enabled)
    return DocumentListResponse(documents=records, total=len(records))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    user: Annotated[dict[str, str] | None, Depends(require_current_user)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> None:
    """Delete a document and all its chunks from the vector store and BM25 index.

    - Admins can delete any document.
    - Regular users can only delete documents they own or legacy documents.
    - Unauthenticated deletion is rejected when auth is configured.
    """
    from app.services.rag_service import RAGService
    try:
        deleted = RAGService(settings).delete_document(document_id, user=user)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected error deleting document %s", document_id)
        raise HTTPException(status_code=500, detail="Document deletion failed.") from error

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")


@router.get("/{document_id}/chunks", response_model=DocumentChunksResponse)
def get_document_chunks(
    document_id: str,
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> DocumentChunksResponse:
    """Retrieve all chunk text and metadata for a specific document with RBAC validation."""
    from app.services.ingestion import DocumentRegistry
    from app.services.rag_service import RAGService

    doc = DocumentRegistry.get(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

    # RBAC validation: admin or owner or legacy (when auth disabled)
    auth_enabled = bool(settings and settings.auth_secret)
    if auth_enabled:
        if not user:
            if doc.owner_id != "legacy":
                raise HTTPException(status_code=401, detail="Authentication required to view document chunks.")
        elif user.get("role") != "admin" and doc.owner_id not in {user.get("username"), "legacy"}:
            raise HTTPException(status_code=403, detail="You do not have permission to view chunks for this document.")

    # Retrieve chunks from Chroma
    try:
        rag = RAGService(settings)
        vector_store = rag._vector_store()
        results = vector_store.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        chunks: list[ChunkDetail] = []
        if results and results.get("documents"):
            doc_texts = results["documents"]
            metadatas = results.get("metadatas", [])
            ids = results.get("ids", [])
            for idx, text in enumerate(doc_texts):
                meta = metadatas[idx] if idx < len(metadatas) else {}
                chunk_id = ids[idx] if idx < len(ids) else f"{document_id}:{idx}"
                chunks.append(
                    ChunkDetail(
                        chunk_id=chunk_id,
                        chunk_index=meta.get("chunk_index", idx),
                        content=text,
                        page=meta.get("page"),
                        allowed_roles=meta.get("allowed_roles"),
                        owner_id=meta.get("owner_id"),
                    )
                )
            chunks.sort(key=lambda c: c.chunk_index)
        return DocumentChunksResponse(
            document_id=document_id,
            filename=doc.filename,
            total_chunks=len(chunks),
            chunks=chunks,
        )
    except Exception as error:
        logger.exception("Failed to retrieve chunks for document %s: %s", document_id, error)
        raise HTTPException(status_code=500, detail="Failed to retrieve document chunks.") from error


