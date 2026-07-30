from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.models.schemas import UploadResponse
from app.core.security import current_user


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
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and Markdown files are supported.")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.upload_dir / f"{uuid4()}{extension}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    stored_path.write_bytes(content)

    try:
        result = DocumentIngestionService(settings).ingest(stored_path, original_filename, user["username"] if user else None)
    except (UnsupportedDocumentError, EmptyDocumentError) as error:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Document ingestion failed.") from error

    return UploadResponse(message="Document ingested", filename=result.filename, chunks=result.chunks)
