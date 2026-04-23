"""Pytest fixtures for the AI Agents test suite.

Provides reusable fixtures for settings, async HTTP client, database
sessions, and mock LangChain components used across unit and
integration tests.
"""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.main import app
from app.models.schemas import ChatGenerateRequest, UserProfile


@pytest.fixture
def settings() -> Settings:
    """Provide test settings with safe defaults.

    Returns:
        A Settings instance configured for testing.
    """
    return Settings(
        environment="development",
        debug=True,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test_golive",
        redis_url="redis://localhost:6379/6",
        llm_provider="openai",
        openai_api_key="sk-test-key-not-real",  # type: ignore[arg-type]
        openai_model="gpt-4-turbo-preview",
        anthropic_api_key="sk-ant-test-key-not-real",  # type: ignore[arg-type]
        anthropic_model="claude-3-opus-20240229",
        llm_temperature=0.7,
        llm_max_tokens=4096,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        langsmith_api_key="",
        langsmith_project="golive-ai-agents-test",
        langchain_tracing_v2=False,
        log_level="DEBUG",
    )


@pytest.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """Provide an async HTTP client for integration tests.

    Yields:
        An AsyncClient configured to send requests to the test app.
    """
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def user_profile() -> UserProfile:
    """Provide a sample UserProfile for testing.

    Returns:
        A UserProfile instance with test data.
    """
    return UserProfile(
        display_name="Juan Pérez",
        avatar_name="Juanito",
        age_range="25_34",
        interests=["tecnología", "fútbol", "música"],
        knowledge_level=2,
    )


@pytest.fixture
def chat_request(user_profile: UserProfile) -> ChatGenerateRequest:
    """Provide a sample ChatGenerateRequest for testing.

    Args:
        user_profile: The test user profile fixture.

    Returns:
        A ChatGenerateRequest instance with test data.
    """
    return ChatGenerateRequest(
        user_id="test-user-123",
        message="Hola, ¿cómo estás hoy?",
        conversation_id="conv-test-456",
        user_profile=user_profile,
        social_data=None,
        health_data=None,
        conversation_history=[
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿Cómo te va?"},
        ],
    )


@pytest.fixture
def mock_llm() -> MagicMock:
    """Provide a mock LangChain LLM for unit testing.

    Returns:
        A MagicMock configured as a BaseChatModel.
    """
    from langchain_core.language_models import BaseChatModel

    return MagicMock(spec=BaseChatModel)
