"""LangSmith configuration for LLM observability and tracing.

Sets up environment variables for LangChain auto-tracing and provides
client/tracer instances for programmatic access to LangSmith.
"""

import logging
import os
from typing import Optional

from langchain_core.tracers import LangChainTracer
from langsmith import Client

from app.config.settings import Settings

logger = logging.getLogger(__name__)


def setup_langsmith(settings: Settings) -> Optional[Client]:
    """Initialize LangSmith for LLM observability.

    Configures the environment variables required by LangChain's
    auto-tracing and returns a LangSmith Client instance for
    programmatic access (e.g., creating datasets, running evaluations).

    Args:
        settings: Application settings with LangSmith configuration.

    Returns:
        A LangSmith Client if configured, None otherwise.
    """
    if not settings.langsmith_api_key:
        logger.warning(
            "LANGSMITH_API_KEY not set — LangSmith tracing is disabled. "
            "Get your key at https://smith.langchain.com"
        )
        return None

    # Set environment variables for LangChain auto-tracing
    os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langchain_tracing_v2).lower()
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    if settings.langchain_tracing_v2:
        logger.info(
            "LangSmith tracing enabled for project: %s",
            settings.langsmith_project,
        )
    else:
        logger.warning(
            "LANGCHAIN_TRACING_V2 is set to false — LangSmith auto-tracing "
            "and @traceable decorators are disabled. Set LANGCHAIN_TRACING_V2=true "
            "in your .env to enable tracing for project: %s",
            settings.langsmith_project,
        )

    return Client(api_key=settings.langsmith_api_key)


def get_tracer(settings: Settings) -> Optional[LangChainTracer]:
    """Get a LangChain tracer for manual tracing.

    Use this when you need to pass a tracer explicitly to a chain
    via the ``callbacks`` parameter.

    Args:
        settings: Application settings with LangSmith configuration.

    Returns:
        A LangChainTracer instance or None if LangSmith is not configured.
    """
    if not settings.langsmith_api_key:
        return None

    return LangChainTracer(
        project_name=settings.langsmith_project,
    )
