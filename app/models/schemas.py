from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    message: str
    filename: str
    chunks: int
    document_id: str | None = None
    owner_id: str | None = None


class DocumentRecord(BaseModel):
    """Metadata about a document that has been ingested into the vector store."""

    document_id: str
    filename: str
    chunks: int
    uploaded_at: str
    owner_id: str
    file_extension: str
    source_sha256: str
    source_size_bytes: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]
    total: int


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(RegisterRequest):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    username: str
    role: str


class UserListResponse(BaseModel):
    users: list[UserProfile]
    total: int


class UpdateRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(admin|user|manager)$")


class ChunkDetail(BaseModel):
    chunk_id: str
    chunk_index: int
    content: str
    page: int | None = None
    allowed_roles: str | None = None
    owner_id: str | None = None


class DocumentChunksResponse(BaseModel):
    document_id: str
    filename: str
    total_chunks: int
    chunks: list[ChunkDetail]


class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str = Field(min_length=1, max_length=10_000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    history: list[ChatMessage] = Field(default_factory=list)
    session_id: str | None = None
    hybrid_search: bool | None = None
    query_expansion: bool | None = None
    enable_reranker: bool | None = None
    enable_semantic_cache: bool | None = None


class Source(BaseModel):
    filename: str
    excerpt: str
    page: int | None = None
    chunk_index: int | None = None
    relevance_score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    session_id: str | None = None
    cached: bool = False


class StreamSourceEvent(BaseModel):
    sources: list[Source]


class StreamTokenEvent(BaseModel):
    token: str


class StreamDoneEvent(BaseModel):
    done: bool = True
    total_tokens: int | None = None
    session_id: str | None = None
    cached: bool = False


class StreamErrorEvent(BaseModel):
    error: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    total: int
