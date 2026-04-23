# GoLive AI Agents - Agent Guidelines

## Project Overview

FastAPI microservice that powers the AI avatar for GoLive. Handles chat response generation, insight extraction, memory management, and semantic search using LangChain, OpenAI, and pgvector.

## Tech Stack

- **Framework:** FastAPI 0.128
- **LLM Orchestration:** LangChain 1.2 + LangChain OpenAI/Anthropic
- **Observability:** LangSmith for tracing
- **Database:** PostgreSQL 16 + pgvector (via SQLAlchemy async + asyncpg)
- **Migrations:** Alembic
- **Cache:** Redis 7
- **Embeddings:** OpenAI text-embedding-3-small (1536 dims)

## Project Structure

```
ai-agents/
  app/
    main.py            # FastAPI app, lifespan, CORS
    agents/            # High-level agent orchestration (NOT_IMPLEMENTED)
    api/
      deps.py          # Dependency injection (DB sessions)
      routes/          # chat.py, health.py, insights.py, memory.py
    chains/
      avatar_chain.py  # LangChain LCEL chain for avatar responses
      insight_chain.py # LangChain chain for insight extraction
    config/
      settings.py      # Pydantic Settings (env vars)
      langsmith.py     # LangSmith tracing setup
    embeddings/        # Embedding utilities (NOT_IMPLEMENTED)
    llm/
      providers.py     # LLM factory (OpenAI/Anthropic)
      callbacks.py     # Token counter, logging callbacks
    memory/            # Memory management (NOT_IMPLEMENTED)
    models/
      database.py      # SQLAlchemy models (InsightModel)
      enums.py         # Enumerations
      schemas.py       # Pydantic request/response schemas
    prompts/
      avatar_prompts.py    # Avatar system prompt builder
      templates/           # .txt prompt templates
    repositories/
      base.py              # Generic async repository
      insight_repository.py # Insight CRUD + vector search
    services/
      chat_service.py      # Chat generation orchestrator
      memory_service.py    # Memory retrieval service
    utils/                 # Utilities (NOT_IMPLEMENTED)
  tests/
    integration/       # API endpoint tests
    unit/              # Schema validation tests
  alembic/             # Database migrations
```

## Coding Standards

### FastAPI Patterns
- Router-based organization: one router per domain in `api/routes/`.
- Dependency injection via `Depends()` for DB sessions, settings.
- Pydantic v2 schemas for all request/response models.
- Use `HTTPException` for error responses with proper status codes.

### LangChain Patterns
- Use LCEL (LangChain Expression Language): `prompt | llm | parser`.
- Prompt templates via `ChatPromptTemplate` (never raw strings).
- Output parsing via `PydanticOutputParser` for structured outputs.
- Custom callbacks for token counting and logging.
- Always add `@traceable(name="...")` decorator to chain methods for LangSmith.

### Async Patterns
- All database operations must be async (`async with session`).
- Use `AsyncGenerator` for streaming responses.
- Use `asyncio.gather()` for parallel independent operations.
- Never block the event loop with sync operations.

### Type Safety
- Type hints on all functions (pyright strict mode).
- Use `SecretStr` for API keys in Settings.
- Use Pydantic models for data validation, not raw dicts.

### Database
- SQLAlchemy 2.0 declarative style with `mapped_column`.
- Async sessions via `asyncpg`.
- Repository pattern: `repositories/` for all DB access.
- Migrations via Alembic (async mode).
- pgvector: IVFFlat index for cosine distance similarity search.

### Configuration
- All settings via Pydantic Settings (from environment variables).
- API keys as `SecretStr` (never logged or exposed).
- CORS origins configurable via `CORS_ALLOWED_ORIGINS` env var.

### Code Style
- Docstrings: Google style with Args, Returns, Raises.
- Imports: stdlib, third-party, local.
- Line length: 100 characters (ruff/black configured).
- Language: English for code, docstrings, and comments.

### Testing
- Framework: pytest + pytest-asyncio.
- Integration tests: test API endpoints with httpx.AsyncClient.
- Unit tests: test schemas, chains (with mocked LLM).

### Observability
- LangSmith tracing enabled via `LANGCHAIN_TRACING_V2=true`.
- All chain methods decorated with `@traceable`.
- Custom `TokenCounterCallback` tracks LLM usage.
- Structured logging with timestamps and module names.
