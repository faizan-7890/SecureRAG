from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.security import current_user
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: Annotated[dict[str, str] | None, Depends(current_user)] = None) -> ChatResponse:
    from app.services.rag_service import RAGService

    question = request.question.strip()
    logger.info(
        "Chat question received: %.120s",
        question,
        extra={"question": question[:120]},
    )

    try:
        return RAGService(get_settings()).answer(
            question=question,
            user=user,
            hybrid_search=request.hybrid_search,
            query_expansion=request.query_expansion,
        )
    except RuntimeError as error:
        logger.error("Chat service error: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected chat error")
        raise HTTPException(status_code=500, detail="Unable to answer the question.") from error
