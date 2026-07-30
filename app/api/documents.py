from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.security import current_user
from app.models.schemas import UploadResponse

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

    logger.info("Upload complete: %s → %d chunks", result.filename, result.chunks, extra={"doc_filename": result.filename, "chunks": result.chunks})
    return UploadResponse(message="Document ingested", filename=result.filename, chunks=result.chunks)
