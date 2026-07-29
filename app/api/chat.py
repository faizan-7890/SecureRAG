from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.models.schemas import ChatRequest, ChatResponse


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    from app.services.rag_service import RAGService

    try:
        return RAGService(get_settings()).answer(request.question.strip())
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Unable to answer the question.") from error
