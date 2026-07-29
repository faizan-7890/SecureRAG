from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    message: str
    filename: str
    chunks: int


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class Source(BaseModel):
    filename: str
    excerpt: str
    page: int | None = None
    chunk_index: int | None = None
    relevance_score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
