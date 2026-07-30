from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.models.schemas import ChatRequest, ChatResponse
from app.core.security import current_user


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: Annotated[dict[str, str] | None, Depends(current_user)] = None) -> ChatResponse:
    from app.services.rag_service import RAGService

    try:
        return RAGService(get_settings()).answer(request.question.strip(), user)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Unable to answer the question.") from error
