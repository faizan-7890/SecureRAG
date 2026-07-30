from fastapi import FastAPI

from app.api import auth, chat, documents
from app.core.config import get_settings


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A production-style retrieval-augmented generation API.",
)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(auth.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}

