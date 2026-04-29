"""FastAPI application entry point for the Go Life AI Agents service.

Configures the FastAPI app with lifespan management, CORS middleware,
and router registration. The lifespan context manager handles startup
and shutdown of shared resources (database, LangSmith).

Run with:
    uvicorn app.main:app --reload --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.internal_auth import require_internal_token
from app.api.routes import audio, chat, health, insights, memory
from app.config.langsmith import setup_langsmith
from app.config.settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    Startup:
        - Load and validate settings.
        - Configure logging level.
        - Initialize LangSmith tracing.
        - Verify database connectivity.

    Shutdown:
        - Clean up database connections.
        - Log shutdown event.

    Args:
        app: The FastAPI application instance.

    Yields:
        None — control returns to the application during its lifetime.
    """
    # ── Startup ─────────────────────────────────────────────────────
    settings = Settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info(
        "Starting Go Life AI Agents v0.1.0 [%s]",
        settings.environment,
    )

    # Initialize LangSmith tracing
    langsmith_client = setup_langsmith(settings)
    if langsmith_client:
        logger.info("LangSmith tracing initialized")

    # Verify database connectivity and create tables
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.models.database import Base

        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")

        # Create tables if they don't exist (insights, conversation_summaries)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created")

        await engine.dispose()
    except Exception:
        logger.warning(
            "Database connection failed — service will start without DB",
            exc_info=True,
        )

    logger.info("AI Agents service ready")

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    logger.info("Shutting down Go Life AI Agents")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI instance with middleware and routes.
    """
    app = FastAPI(
        title="Go Life AI Agents",
        description=(
            "AI-powered avatar service using LangChain and LangSmith. "
            "Handles conversation generation, memory management, "
            "insight extraction, and sentiment analysis."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS Middleware ─────────────────────────────────────────────
    settings = Settings()
    cors_origins_raw = settings.cors_allowed_origins
    if cors_origins_raw == "*":
        cors_origins: list[str] = ["*"]
    else:
        cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register Routers ───────────────────────────────────────────
    # /health stays public (liveness probe). All /internal/* endpoints are
    # protected by the shared X-Internal-Token header; see app/api/internal_auth.py.
    app.include_router(health.router)

    internal_guard = [Depends(require_internal_token)]
    app.include_router(chat.router, dependencies=internal_guard)
    app.include_router(memory.router, dependencies=internal_guard)
    app.include_router(insights.router, dependencies=internal_guard)
    app.include_router(audio.router, dependencies=internal_guard)

    return app


app = create_app()
