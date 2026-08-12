import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api import auth, chat, documents
from app.core.config import get_settings
from app.core.logging import request_id_ctx, setup_logging


settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter — in-memory, IP-keyed (use Redis backend for production)
# ---------------------------------------------------------------------------

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_global],
    storage_uri="memory://",
)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A production-style retrieval-augmented generation API.",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ---------------------------------------------------------------------------
# Request-logging middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID and log every request/response pair."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = uuid4().hex[:12]
        request_id_ctx.set(rid)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        logger.info(
            "%s %s → %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = rid
        return response


app.add_middleware(RequestLoggingMiddleware)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(auth.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}

