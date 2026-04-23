"""Dependency injection for FastAPI endpoints.

Provides cacheable settings, database sessions, and LangChain component
factories as FastAPI dependencies. Type aliases simplify endpoint signatures.
"""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import Settings

logger = logging.getLogger(__name__)


# ── Settings ────────────────────────────────────────────────────────────


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Uses ``@lru_cache`` to ensure a single Settings instance is created
    and reused across all requests during the application lifetime.

    Returns:
        The application Settings instance.
    """
    return Settings()


# ── Database Session ────────────────────────────────────────────────────


def _get_async_session_maker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    """Create an async session maker for the database.

    Args:
        settings: Application settings with database URL.

    Returns:
        An async session maker bound to the configured database.
    """
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=5,
        max_overflow=10,
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AsyncSession]:
    """Yield an async database session.

    Creates a session from the async session maker, yields it for
    the request handler, and ensures it is closed afterward.

    Args:
        settings: Application settings (injected).

    Yields:
        An AsyncSession connected to the database.
    """
    session_maker = _get_async_session_maker(settings)
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


# ── LLM Provider ────────────────────────────────────────────────────────


def get_llm_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BaseChatModel:
    """Get the configured LLM provider as a FastAPI dependency.

    Args:
        settings: Application settings (injected).

    Returns:
        A LangChain BaseChatModel instance.
    """
    from app.llm.providers import get_llm

    return get_llm(settings)


# ── Type Aliases ────────────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LLMDep = Annotated[BaseChatModel, Depends(get_llm_provider)]
