"""Application settings using Pydantic Settings.

Loads configuration from environment variables and .env files.
All settings are validated at startup with Pydantic v2.
"""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        environment: Deployment environment (development, staging, production).
        debug: Enable debug mode with verbose logging.
        database_url: PostgreSQL connection string with asyncpg driver.
        redis_url: Redis connection string for caching.
        llm_provider: LLM provider to use (openai or anthropic).
        openai_api_key: OpenAI API key for GPT models.
        openai_model: OpenAI model name to use.
        anthropic_api_key: Anthropic API key for Claude models.
        anthropic_model: Anthropic model name to use.
        llm_temperature: Sampling temperature for LLM responses.
        llm_max_tokens: Maximum tokens in LLM response.
        embedding_model: OpenAI embedding model name.
        embedding_dimensions: Embedding vector dimensionality.
        langsmith_api_key: LangSmith API key for observability.
        langsmith_project: LangSmith project name for tracing.
        langchain_tracing_v2: Enable LangChain v2 tracing.
        log_level: Python logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ─────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://golive:password@localhost:5432/golive",
        description="PostgreSQL connection string with asyncpg driver",
    )

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/5",
        description="Redis connection string for caching (DB 5 for go-live)",
    )

    # ── LLM Provider ────────────────────────────────────────────────────
    llm_provider: Literal["openai", "anthropic"] = "openai"

    # ── OpenAI ──────────────────────────────────────────────────────────
    openai_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="OpenAI API key",
    )
    openai_model: str = "o4-mini"

    # ── Anthropic ───────────────────────────────────────────────────────
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Anthropic API key",
    )
    anthropic_model: str = "claude-3-opus-20240229"

    # ── LLM Settings ───────────────────────────────────────────────────
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=4096, ge=1)

    # ── Embeddings ──────────────────────────────────────────────────────
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1)

    # ── LangSmith (Observability) ───────────────────────────────────────
    langsmith_api_key: str = Field(
        default="",
        description="LangSmith API key for tracing",
    )
    langsmith_project: str = "golive-ai-agents"
    langchain_tracing_v2: bool = True

    # ── Web Search ──────────────────────────────────────────────────────
    web_search_enabled: bool = Field(
        default=True,
        description="Enable web search tool-calling for the avatar agent",
    )
    # When True the agent verifies external facts proactively (more Tavily calls).
    # Set False in tests or cost-sensitive environments.
    web_search_proactive_factual: bool = Field(
        default=True,
        description=(
            "Allow the agent to call web_search proactively to verify factual claims, "
            "even when the user did not explicitly ask for a search"
        ),
    )
    tavily_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Tavily Search API key for real-time web search",
    )
    web_search_max_results: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of web search results to return",
    )
    web_search_max_calls: int = Field(
        default=5,
        ge=1,
        le=20,
        description=(
            "Maximum total tool calls (web_search + fetch_urls) the agent may make "
            "per conversation turn. Drives the LangGraph recursion_limit."
        ),
    )
    fetch_url_max_urls: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum URLs per fetch_urls tool call (Tavily Extract)",
    )

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_allowed_origins: str = Field(
        default="*",
        description="Comma-separated allowed origins, or '*' for all (dev only)",
    )

    # ── Internal auth ────────────────────────────────────────────────────
    # Shared secret between Rails and this service. Every /internal/*
    # request must carry it as the X-Internal-Token header.
    internal_token: str = Field(
        default="",
        description="Shared secret with the Rails backend (X-Internal-Token).",
    )

    # ── Audio transcription ─────────────────────────────────────────────
    # Provider for audio transcription. v1 ships "openai" only; "self_hosted"
    # is reserved for a future faster-whisper / whisper.cpp deployment.
    audio_transcription_provider: str = Field(
        default="openai",
        description="Audio transcription provider; one of {openai, self_hosted}.",
    )
    # Default model is gpt-4o-mini-transcribe (~$0.003/min, text-only).
    # Switch to "whisper-1" for native segment timestamps at 2× the cost.
    audio_transcription_model: str = Field(
        default="gpt-4o-mini-transcribe",
        description="Audio transcription model id (provider-specific).",
    )

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations.

        Replaces asyncpg driver with psycopg2 for synchronous operations.

        Returns:
            Synchronous PostgreSQL connection string.
        """
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )
