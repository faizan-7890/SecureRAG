from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    message: str
    filename: str
    chunks: int


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(RegisterRequest):
    pass

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
