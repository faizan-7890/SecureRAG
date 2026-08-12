from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.security import current_user
from app.models.schemas import DocumentListResponse, UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), user: Annotated[dict[str, str] | None, Depends(current_user)] = None) -> UploadResponse:
    from app.services.ingestion import (
        DocumentIngestionService,
        EmptyDocumentError,
        UnsupportedDocumentError,
    )

    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    settings = get_settings()
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
) -> DocumentListResponse:
    """List all ingested documents visible to the authenticated caller.

    - Admins see every document.
    - Regular users see only their own documents and 'legacy' (unauthenticated) uploads.
    - Unauthenticated callers (auth not configured) see all documents.
    """
    from app.services.ingestion import DocumentRegistry

    owner_id = user.get("username") if user else None
    role = user.get("role") if user else None
    records = DocumentRegistry.all(owner_id=owner_id, role=role)
    return DocumentListResponse(documents=records, total=len(records))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
) -> None:
    """Delete a document and all its chunks from the vector store and BM25 index.

    - Admins can delete any document.
    - Regular users can only delete documents they own.
    """
    from app.services.rag_service import RAGService

    settings = get_settings()
    try:
        deleted = RAGService(settings).delete_document(document_id, user=user)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected error deleting document %s", document_id)
        raise HTTPException(status_code=500, detail="Document deletion failed.") from error

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")

