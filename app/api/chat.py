from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.security import current_user
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    StreamDoneEvent,
    StreamErrorEvent,
    StreamSourceEvent,
    StreamTokenEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
    x_openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
) -> ChatResponse:
    from app.services.rag_service import RAGService

    question = request.question.strip()
    logger.info(
        "Chat question received: %.120s (session=%s)",
        question,
        request.session_id,
        extra={"question": question[:120], "session_id": request.session_id},
    )

    settings = get_settings()
    if x_openai_api_key:
        settings = settings.model_copy(update={"openai_api_key": x_openai_api_key})

    try:
        return RAGService(settings).answer(
            question=question,
            user=user,
            history=request.history,
            session_id=request.session_id,
            hybrid_search=request.hybrid_search,
            query_expansion=request.query_expansion,
        )
    except RuntimeError as error:
        logger.error("Chat service error: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected chat error")
        raise HTTPException(status_code=500, detail="Unable to answer the question.") from error


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    user: Annotated[dict[str, str] | None, Depends(current_user)] = None,
    x_openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
) -> StreamingResponse:
    """Stream token-by-token answer via Server-Sent Events (SSE)."""
    from app.services.rag_service import RAGService

    question = request.question.strip()
    logger.info(
        "Chat stream requested: %.120s (session=%s)",
        question,
        request.session_id,
        extra={"question": question[:120], "session_id": request.session_id},
    )

    settings = get_settings()
    if x_openai_api_key:
        settings = settings.model_copy(update={"openai_api_key": x_openai_api_key})

    def event_generator():
        try:
            service = RAGService(settings)
            for event in service.answer_stream(
                question=question,
                user=user,
                history=request.history,
                session_id=request.session_id,
                hybrid_search=request.hybrid_search,
                query_expansion=request.query_expansion,
            ):
                if isinstance(event, StreamSourceEvent):
                    yield f"event: sources\ndata: {event.model_dump_json()}\n\n"
                elif isinstance(event, StreamTokenEvent):
                    yield f"event: token\ndata: {event.model_dump_json()}\n\n"
                elif isinstance(event, StreamDoneEvent):
                    yield f"event: done\ndata: {event.model_dump_json()}\n\n"
                elif isinstance(event, StreamErrorEvent):
                    yield f"event: error\ndata: {event.model_dump_json()}\n\n"
        except Exception as error:
            logger.exception("Error during event generation")
            err_event = StreamErrorEvent(error=str(error))
            yield f"event: error\ndata: {err_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
