"""Application factory and ASGI entrypoint for CarbonSaathi."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import configure_security_middleware
from app.routes import auth, health, users

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown.

    Configures logging on startup and emits structured lifecycle events.

    Args:
        app: The FastAPI application (unused, required by the lifespan protocol).

    Yields:
        Control back to the running application.
    """
    configure_logging()
    settings = get_settings()
    logger.info("application.startup", env=settings.app_env)
    try:
        yield
    finally:
        logger.info("application.shutdown")


async def _rate_limit_handler(request: Request, exc: Exception) -> Response:
    """Return a 429 JSON response when a rate limit is exceeded.

    Args:
        request: The incoming request (unused).
        exc: The raised :class:`RateLimitExceeded` error (unused).

    Returns:
        A JSON response with HTTP status 429.
    """
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A fully configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="CarbonSaathi",
        description=(
            "A personal AI companion that helps Indian metro professionals "
            "track and reduce their everyday carbon footprint."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    configure_security_middleware(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(users.router, prefix="/api")

    return app


app = create_app()
