"""Health check endpoint for the AI Agents service.

Provides a /health endpoint that verifies the service is running,
the database is reachable, and LangSmith tracing is configured.
"""

import logging

from fastapi import APIRouter, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSessionDep, SettingsDep
from app.models.schemas import HealthCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

SERVICE_VERSION = "0.1.0"


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description="Verify that the AI Agents service and its dependencies are operational.",
)
async def health_check(
    settings: SettingsDep,
) -> HealthCheckResponse:
    """Check the health of the AI Agents service.

    Verifies:
    - The service itself is running.
    - LangSmith tracing configuration status.

    Note: Database connectivity is checked via a lightweight query
    only when a session is available. The health endpoint remains
    functional even if the database is unreachable.

    Args:
        settings: Application settings (injected).

    Returns:
        HealthCheckResponse with status of each dependency.
    """
    # Check database connectivity
    db_status = "disconnected"
    try:
        from app.api.deps import _get_async_session_maker

        session_maker = _get_async_session_maker(settings)
        async with session_maker() as session:
            await session.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        db_status = "disconnected"

    # Check LangSmith configuration
    langsmith_status = "enabled" if settings.langsmith_api_key else "disabled"

    return HealthCheckResponse(
        status="healthy",
        version=SERVICE_VERSION,
        environment=settings.environment,
        database=db_status,
        langsmith=langsmith_status,
    )
