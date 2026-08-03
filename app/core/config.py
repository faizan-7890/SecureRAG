from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuration loaded from environment variables and the project `.env` file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "SecureRAG"
    environment: str = "development"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    chroma_path: Path = Field(default=PROJECT_ROOT / "chroma_db")
    upload_dir: Path = Field(default=PROJECT_ROOT / "data" / "uploads")
    chroma_collection: str = "securerag_documents"
    top_k: int = Field(default=4, ge=1, le=20)
    retrieval_candidate_k: int = Field(default=12, ge=1, le=50)
    similarity_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    citation_excerpt_chars: int = Field(default=350, ge=100, le=1_000)
    chunk_size: int = Field(default=900, ge=100)
    chunk_overlap: int = Field(default=150, ge=0)
    auth_secret: str | None = None
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    auth_bootstrap_admin: str | None = None
    auth_bootstrap_password: str | None = None
    log_level: str = "INFO"
    enable_hybrid_search: bool = True
    enable_query_expansion: bool = False
    dense_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    sparse_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    rrf_k: int = Field(default=60, ge=1, le=200)
    query_expansion_count: int = Field(default=3, ge=1, le=5)
    bm25_index_path: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
