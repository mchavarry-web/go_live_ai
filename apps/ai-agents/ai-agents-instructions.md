# AI Agents - Instrucciones para Desarrolladores

## 1. Contexto del Proyecto

### Visión General de Go Life

**Go Life** es una aplicación móvil que crea un avatar digital personalizado. El avatar:
- Conoce al usuario progresivamente a través de conversaciones
- Se personaliza usando datos de redes sociales (Facebook, Google)
- Recuerda conversaciones anteriores y extrae insights
- Usa datos de salud/actividad para contextualizar respuestas

**Timeline:** MVP en 3 semanas para demo a inversores (Insurtech NY, 26 de marzo)

### Arquitectura General

```
┌─────────────────┐
│   Mobile App    │  ← React Native / Flutter
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐                        ┌─────────────────┐
│  API-BACKEND    │  ◄─── HTTP interno ──► │   AI-AGENTS     │
│  (Node.js)      │                        │  (Este proyecto) │
│                 │                        │                 │
│  Puerto: 3000   │                        │  Puerto: 8000   │
└────────┬────────┘                        └────────┬────────┘
         │                                          │
         └──────────────┬───────────────────────────┘
                        ▼
                ┌───────────────┐
                │  PostgreSQL   │  ← Base de datos compartida
                │  + pgvector   │  ← Extensión para embeddings
                └───────────────┘
                        │
                ┌───────────────┐
                │  LangSmith    │  ← Observabilidad de LLMs
                └───────────────┘
```

### Tu Rol: AI Agents

Eres el **cerebro de inteligencia artificial** del sistema. Manejas toda la lógica relacionada con IA usando **LangChain** como framework principal y **LangSmith** para observabilidad.

**Responsabilidades:**
- Generar respuestas del avatar usando LangChain chains (OpenAI/Claude)
- Gestionar la memoria del avatar con LangChain Memory components
- Extraer insights usando LangChain chains con PydanticOutputParser
- Generar y buscar embeddings con LangChain pgvector integration
- Construir prompts personalizados con ChatPromptTemplate
- Análisis de sentimiento y emociones mediante chains dedicadas
- Monitorear todas las llamadas LLM con LangSmith (@traceable)

**NO eres responsable de:**
- Autenticación de usuarios (eso lo hace api-backend)
- Conexión con redes sociales (eso lo hace api-backend)
- Almacenamiento de conversaciones (eso lo hace api-backend)
- Comunicación directa con la app móvil (todo pasa por api-backend)

**Comunicación:**
- Solo `api-backend` puede llamarte (endpoints `/internal/*`)
- No expones endpoints públicos
- Recibes datos ya procesados (perfil, datos sociales, historial)

---

## 2. Stack Tecnológico

```
Runtime:            Python 3.11+
Framework:          FastAPI 0.100+
Validación:         Pydantic v2
ORM:                SQLAlchemy 2.0 (async)
Base de datos:      PostgreSQL 16 + pgvector
Cache:              Redis

# LangChain Ecosystem
LangChain:          >= 0.1.0
LangChain Core:     >= 0.1.0
LangChain OpenAI:   >= 0.0.5
LangChain Anthropic: >= 0.1.1
LangChain Postgres: >= 0.0.1
LangSmith:          >= 0.0.87 (observabilidad)

LLM Providers:      ChatOpenAI (GPT-4) / ChatAnthropic (Claude) vía LangChain
Embeddings:         OpenAIEmbeddings (text-embedding-3-small) vía LangChain

Type Checking:      Pyright (strict mode)
Linting:            Ruff
Formatting:         Black + isort
Testing:            Pytest + pytest-asyncio
```

---

## 3. Estructura del Proyecto

```
ai-agents/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py             # Pydantic Settings
│   │   ├── logging.py              # Configuración de logging
│   │   └── langsmith.py            # Configuración de LangSmith
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                 # Dependency injection (LangChain wiring)
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py             # /internal/chat/*
│   │       ├── memory.py           # /internal/memory/*
│   │       ├── insights.py         # /internal/insights/*
│   │       ├── embeddings.py       # /internal/embeddings/*
│   │       └── health.py           # /health
│   │
│   ├── chains/                     # LangChain chains
│   │   ├── __init__.py
│   │   ├── avatar_chain.py         # Chain principal de conversación del avatar
│   │   ├── insight_chain.py        # Chain de extracción de insights
│   │   └── sentiment_chain.py      # Chain de análisis de sentimiento
│   │
│   ├── prompts/                    # LangChain prompt templates
│   │   ├── __init__.py
│   │   ├── avatar_prompts.py       # System prompts del avatar
│   │   ├── insight_prompts.py      # Prompts de extracción de insights
│   │   └── templates/              # Archivos de plantillas de prompts
│   │       ├── avatar_system.txt
│   │       └── insight_extraction.txt
│   │
│   ├── memory/                     # LangChain memory components
│   │   ├── __init__.py
│   │   ├── conversation_memory.py  # Buffer de conversación
│   │   ├── vector_memory.py        # Vector store memory (pgvector)
│   │   └── combined_memory.py      # Estrategia de memoria combinada
│   │
│   ├── agents/                     # LangChain agents (si se necesitan)
│   │   ├── __init__.py
│   │   └── avatar_agent.py         # Agente del avatar con tools
│   │
│   ├── llm/                        # Configuración de proveedores LLM
│   │   ├── __init__.py
│   │   ├── providers.py            # Factory LangChain (ChatOpenAI/ChatAnthropic)
│   │   └── callbacks.py            # Custom LangChain callbacks
│   │
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── embedder.py             # LangChain embeddings wrapper
│   │   └── vector_store.py         # Operaciones con pgvector via LangChain
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py              # Pydantic models (API)
│   │   ├── database.py             # SQLAlchemy models
│   │   └── enums.py                # Enumeraciones
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py                 # Base repository
│   │   ├── insight_repository.py   # CRUD insights
│   │   └── memory_repository.py    # CRUD memoria
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── chat_service.py         # Orquestación del chat (usa chains)
│   │   ├── memory_service.py       # Lógica de memoria
│   │   └── insight_service.py      # Lógica de insights
│   │
│   └── utils/
│       ├── __init__.py
│       ├── text.py                 # Utilidades de texto
│       ├── retry.py                # Retry logic
│       └── langsmith_utils.py      # Helpers de LangSmith
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Fixtures de pytest
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_avatar_chain.py
│   │   ├── test_insight_chain.py
│   │   ├── test_sentiment_chain.py
│   │   └── test_vector_memory.py
│   └── integration/
│       ├── __init__.py
│       └── test_chat_endpoint.py
│
├── alembic/                        # Migraciones (si se usa Alembic)
│   ├── versions/
│   └── env.py
│
├── pyproject.toml                  # Configuración del proyecto
├── requirements.txt                # Dependencias
├── requirements-dev.txt            # Dependencias de desarrollo
├── .env.example
├── Dockerfile
└── README.md
```

---

## 4. Guidelines de Código

### 4.1 Pyright Strict Mode

```toml
# pyproject.toml
[tool.pyright]
pythonVersion = "3.11"
typeCheckingMode = "strict"
reportMissingImports = true
reportMissingTypeStubs = true
reportUnusedImport = true
reportUnusedVariable = true
reportUnusedFunction = true
reportPrivateUsage = true
reportConstantRedefinition = true
reportIncompatibleMethodOverride = true
reportIncompatibleVariableOverride = true
reportUntypedFunctionDecorator = true
reportUntypedClassDecorator = true
reportUntypedBaseClass = true
reportUntypedNamedTuple = true
reportCallInDefaultInitializer = true
reportUnnecessaryIsInstance = true
reportUnnecessaryCast = true
reportAssertAlwaysTrue = true
```

### 4.2 Ruff Configuration (Linting)

```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 100
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
    "TCH",    # flake8-type-checking
    "PTH",    # flake8-use-pathlib
    "RUF",    # Ruff-specific rules
    "ASYNC",  # flake8-async
    "S",      # flake8-bandit (security)
]
ignore = [
    "E501",   # line too long (handled by black)
    "B008",   # do not perform function calls in argument defaults
]

[tool.ruff.per-file-ignores]
"tests/*" = ["S101"]  # Allow assert in tests

[tool.ruff.isort]
known-first-party = ["app"]
```

### 4.3 Black Configuration

```toml
# pyproject.toml
[tool.black]
line-length = 100
target-version = ["py311"]
include = '\.pyi?$'
```

### 4.4 Convenciones de Nombrado

```python
# ✅ CORRECTO

# Clases: PascalCase
class AvatarChain:
    pass

class InsightExtractionChain:
    pass

class ChatGenerateRequest:
    pass

# Funciones y métodos: snake_case
def get_avatar_system_prompt(profile: UserProfile) -> str:
    pass

async def extract_insights(text: str) -> list[ExtractedInsight]:
    pass

# Variables: snake_case
user_profile = get_user_profile()
avatar_chain = AvatarChain(llm=llm)
conversation_history: list[BaseMessage] = []

# Constantes: SCREAMING_SNAKE_CASE
MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
EMBEDDING_MODEL = "text-embedding-3-small"

# Módulos y archivos: snake_case
# avatar_chain.py
# insight_chain.py
# avatar_prompts.py

# Type aliases: PascalCase
UserId = str
EmbeddingVector = list[float]

# ❌ INCORRECTO
class avatarChain:          # Debe ser PascalCase
def GenerateResponse():     # Debe ser snake_case
userProfile = {}            # Debe ser snake_case
max_tokens = 4096           # Constante, debe ser SCREAMING_SNAKE_CASE
```

### 4.5 Type Hints Obligatorios

```python
# ✅ CORRECTO - Todos los tipos explícitos

from typing import Optional, Sequence
from collections.abc import AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document

async def generate_chat_response(
    user_id: str,
    message: str,
    history: Sequence[dict[str, str]],
    temperature: float = 0.7,
) -> ChatGenerateResponse:
    """Generate a chat response from the avatar."""
    ...

def build_avatar_chain(
    llm: BaseChatModel,
) -> AvatarChain:
    """Build an avatar conversation chain."""
    ...

async def search_similar_insights(
    query: str,
    user_id: str,
    k: int = 5,
) -> list[Document]:
    """Search for similar insights using vector similarity."""
    ...

# ❌ INCORRECTO - Sin tipos
def generate_response(message, history):
    ...
```

### 4.6 Docstrings (Google Style)

```python
async def generate_chat_response(
    self,
    request: ChatGenerateRequest,
) -> ChatGenerateResponse:
    """Generate a personalized response from the avatar using LangChain.

    This method orchestrates the entire response generation process:
    1. Retrieves relevant memories from the vector store via LangChain pgvector
    2. Builds a personalized system prompt using ChatPromptTemplate
    3. Invokes the avatar chain (prompt | llm | output_parser)
    4. Extracts new insights using the InsightExtractionChain
    5. All steps are traced automatically via LangSmith @traceable

    Args:
        request: The chat generation request containing user message,
            profile, and conversation history.

    Returns:
        A ChatGenerateResponse containing the avatar's response,
        detected emotions, and any new insights extracted.

    Raises:
        LLMError: If the LLM service is unavailable or returns an error.
        MemoryError: If there's an issue accessing the memory store.

    Example:
        >>> request = ChatGenerateRequest(
        ...     user_id="123",
        ...     message="How was your day?",
        ...     conversation_history=[],
        ... )
        >>> response = await chat_service.generate_response(request)
        >>> print(response.response)
        "It was great! Tell me about yours..."
    """
    ...
```

### 4.7 Pydantic Models

```python
# models/schemas.py
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class InsightCategory(str, Enum):
    """Categories for user insights."""

    PERSONAL_HISTORY = "personal_history"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    EMOTION = "emotion"
    HEALTH = "health"


class UserProfile(BaseModel):
    """User profile data received from api-backend."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        frozen=True,  # Inmutable
    )

    display_name: str = Field(..., min_length=1, max_length=100)
    avatar_name: str = Field(..., min_length=1, max_length=50)
    age_range: Optional[str] = None
    interests: list[str] = Field(default_factory=list)
    knowledge_level: int = Field(default=1, ge=1, le=5)

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, v: list[str]) -> list[str]:
        """Ensure interests are lowercase and unique."""
        return list({interest.lower().strip() for interest in v})


class ChatGenerateRequest(BaseModel):
    """Request to generate a chat response."""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: str = Field(..., min_length=1)
    user_profile: UserProfile
    social_data: Optional[dict[str, object]] = None
    health_data: Optional[dict[str, object]] = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class Insight(BaseModel):
    """An insight extracted from user interaction."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    category: InsightCategory
    content: str = Field(..., max_length=1000)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    created_at: datetime


class ChatGenerateResponse(BaseModel):
    """Response from chat generation."""

    response: str
    emotion_detected: Optional[str] = None
    new_insights: list[Insight] = Field(default_factory=list)
    suggested_followup: Optional[str] = None
    tokens_used: int = Field(..., ge=0)
```

### 4.8 Async/Await Patterns

```python
# ✅ CORRECTO - Async consistente con LangChain

import asyncio
from typing import Sequence

from langsmith import traceable

from app.chains.avatar_chain import AvatarChain
from app.chains.insight_chain import InsightExtractionChain
from app.chains.sentiment_chain import SentimentChain
from app.memory.vector_memory import VectorMemory
from app.models.schemas import ChatGenerateRequest, ChatGenerateResponse


@traceable(name="process_message", run_type="chain")
async def process_message(
    request: ChatGenerateRequest,
    avatar_chain: AvatarChain,
    insight_chain: InsightExtractionChain,
    sentiment_chain: SentimentChain,
    vector_memory: VectorMemory,
) -> ChatGenerateResponse:
    """Process a chat message with concurrent operations."""

    # Ejecutar operaciones independientes en paralelo
    similar_docs, sentiment_result = await asyncio.gather(
        vector_memory.search_similar(
            query=request.message,
            user_id=request.user_id,
            k=5,
        ),
        sentiment_chain.invoke(request.message),
    )

    relevant_insights = [doc.page_content for doc in similar_docs]

    # Operación secuencial: generar respuesta del avatar
    response_text = await avatar_chain.invoke(
        request=request,
        relevant_insights=relevant_insights,
    )

    # Extraer insights en paralelo (no bloquea respuesta)
    new_insights = await insight_chain.invoke(
        message=request.message,
        context="\n".join(relevant_insights),
    )

    return ChatGenerateResponse(
        response=response_text,
        emotion_detected=sentiment_result.primary_emotion,
        new_insights=new_insights,
        tokens_used=0,  # LangSmith rastrea tokens automáticamente
    )


# ❌ INCORRECTO - Operaciones secuenciales innecesarias
async def process_message_bad(
    request: ChatGenerateRequest,
    vector_memory: VectorMemory,
    sentiment_chain: SentimentChain,
) -> ChatGenerateResponse:
    # Esto es más lento porque espera cada operación
    similar_docs = await vector_memory.search_similar(...)
    sentiment = await sentiment_chain.invoke(...)  # Podría ser paralelo
    ...
```

### 4.9 Dependency Injection con FastAPI (LangChain Wiring)

```python
# api/deps.py
from functools import lru_cache
from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.llm.providers import get_llm, get_embeddings
from app.chains.avatar_chain import AvatarChain
from app.chains.insight_chain import InsightExtractionChain
from app.chains.sentiment_chain import SentimentChain
from app.memory.vector_memory import VectorMemory
from app.services.chat_service import ChatService
from app.repositories.insight_repository import InsightRepository


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


def get_insight_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InsightRepository:
    """Get insight repository instance."""
    return InsightRepository(session)


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatService:
    """Build chat service with all LangChain components.

    Wires up LLM provider, chains, memory, and embeddings
    using LangChain's ChatOpenAI/ChatAnthropic.
    """
    llm = get_llm(settings)
    embeddings = get_embeddings(settings)

    avatar_chain = AvatarChain(llm=llm)
    insight_chain = InsightExtractionChain(llm=llm)
    sentiment_chain = SentimentChain(llm=llm)
    vector_memory = VectorMemory(embeddings=embeddings, settings=settings)

    return ChatService(
        avatar_chain=avatar_chain,
        insight_chain=insight_chain,
        sentiment_chain=sentiment_chain,
        vector_memory=vector_memory,
    )


# Type aliases para anotaciones limpias
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
```

### 4.10 Router Implementation

```python
# api/routes/chat.py
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langsmith import traceable
from pydantic import ValidationError

from app.api.deps import ChatServiceDep
from app.models.schemas import ChatGenerateRequest, ChatGenerateResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/internal/chat", tags=["Chat"])


@router.post(
    "/generate",
    response_model=ChatGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate avatar response",
    description="Generate a personalized response from the user's avatar using LangChain.",
)
@traceable(name="chat_generate_endpoint")
async def generate_chat_response(
    request: ChatGenerateRequest,
    chat_service: ChatServiceDep,
) -> ChatGenerateResponse:
    """Generate a chat response from the avatar.

    This endpoint is called by api-backend when a user sends a message.
    It orchestrates the response generation process using LangChain chains
    including memory retrieval, prompt building, and LLM invocation.
    All calls are traced via LangSmith.
    """
    try:
        response = await chat_service.generate_response(request)
        return response
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response",
        ) from e


@router.post(
    "/stream",
    summary="Stream avatar response",
    description="Stream a response from the avatar in real-time using LangChain streaming.",
)
@traceable(name="chat_stream_endpoint")
async def stream_chat_response(
    request: ChatGenerateRequest,
    chat_service: ChatServiceDep,
) -> StreamingResponse:
    """Stream a chat response for real-time display."""

    async def generate():
        async for chunk in chat_service.stream_response(request):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

### 4.11 Error Handling

```python
# core/exceptions.py
from typing import Optional


class AIAgentsError(Exception):
    """Base exception for AI Agents service."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class LLMError(AIAgentsError):
    """Error related to LLM operations."""

    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded on LLM API."""

    pass


class LLMContextLengthError(LLMError):
    """Context length exceeded for LLM."""

    pass


class MemoryError(AIAgentsError):
    """Error related to memory operations."""

    pass


class EmbeddingError(AIAgentsError):
    """Error related to embedding operations."""

    pass


class ChainError(AIAgentsError):
    """Error related to LangChain chain execution."""

    pass


# Uso en el código con LangChain
from langchain_core.language_models import BaseChatModel
from langchain_core.exceptions import OutputParserException
from langsmith import traceable


@traceable(name="safe_chain_invoke")
async def safe_chain_invoke(
    chain: BaseChatModel,
    inputs: dict[str, object],
) -> str:
    """Safely invoke a LangChain chain with error handling."""
    try:
        result = await chain.ainvoke(inputs)
        return str(result)
    except OutputParserException as e:
        raise ChainError(
            message="Failed to parse chain output",
            details={"parser_error": str(e)},
        ) from e
    except Exception as e:
        error_str = str(e).lower()
        if "rate_limit" in error_str or "429" in error_str:
            raise LLMRateLimitError(
                message="Rate limit exceeded",
                details={"original_error": str(e)},
            ) from e
        if "context_length" in error_str or "maximum context" in error_str:
            raise LLMContextLengthError(
                message="Context too long for LLM",
                details={"original_error": str(e)},
            ) from e
        raise LLMError(message=str(e)) from e
```

### 4.12 LangChain-Specific Guidelines

Las siguientes reglas se aplican a toda chain, prompt y componente LangChain:

1. **Todas las chains deben usar `@traceable`** para asegurar trazabilidad en LangSmith:

```python
from langsmith import traceable

@traceable(name="my_chain_operation", run_type="chain")
async def my_chain_method(self, input_data: str) -> str:
    ...
```

2. **Usar `ChatPromptTemplate` para construcción de prompts** (nunca strings crudos):

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])
```

3. **Usar `PydanticOutputParser` para salidas estructuradas**:

```python
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field


class MyOutput(BaseModel):
    field_a: str = Field(description="Descripción del campo A")
    field_b: float = Field(description="Descripción del campo B")

parser = PydanticOutputParser(pydantic_object=MyOutput)
```

4. **Usar `RunnableSequence` / operador `|` para composición de chains**:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_template("Tell me about {topic}")
chain = prompt | llm | StrOutputParser()
result = await chain.ainvoke({"topic": "LangChain"})
```

5. **LLM Provider Factory siempre via LangChain** (nunca clientes directos de OpenAI/Anthropic):

```python
# ✅ CORRECTO - Usar LangChain wrappers
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

llm = ChatOpenAI(model="gpt-4-turbo-preview", temperature=0.7)

# ❌ INCORRECTO - Nunca usar clientes directos
from openai import AsyncOpenAI  # NO usar esto
client = AsyncOpenAI(api_key="...")  # NO usar esto
```

---

## 5. Componentes Principales (LangChain)

### 5.1 LLM Provider Factory

```python
# llm/providers.py
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic

from app.config.settings import Settings


def get_llm(settings: Settings) -> BaseChatModel:
    """Get the configured LLM provider via LangChain.

    Factory function that returns the appropriate LangChain chat model
    based on the configured provider (OpenAI or Anthropic).

    Args:
        settings: Application settings with provider configuration.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the configured provider is not supported.
    """
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.openai_api_key,
        )
    elif settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=settings.anthropic_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            api_key=settings.anthropic_api_key,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def get_embeddings(settings: Settings) -> Embeddings:
    """Get the configured embeddings model via LangChain.

    Args:
        settings: Application settings with embedding configuration.

    Returns:
        A LangChain Embeddings instance.
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )
```

### 5.2 LangChain Callbacks

```python
# llm/callbacks.py
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

import logging

logger = logging.getLogger(__name__)


class TokenCounterCallback(AsyncCallbackHandler):
    """Callback to track token usage across chain invocations."""

    def __init__(self) -> None:
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Track token usage when LLM call completes."""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_prompt_tokens += usage.get("prompt_tokens", 0)
            self.total_completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)

    def reset(self) -> None:
        """Reset token counters."""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0


class LoggingCallback(AsyncCallbackHandler):
    """Callback to log chain execution events."""

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Log when a chain starts executing."""
        chain_name = serialized.get("name", "unknown")
        logger.info("Chain started: %s (run_id=%s)", chain_name, run_id)

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Log when a chain encounters an error."""
        logger.error("Chain error (run_id=%s): %s", run_id, str(error))
```

### 5.3 Avatar Chain (Conversación Principal)

```python
# chains/avatar_chain.py
from typing import Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langsmith import traceable

from app.models.schemas import ChatGenerateRequest, UserProfile
from app.prompts.avatar_prompts import get_avatar_system_prompt


class AvatarChain:
    """LangChain chain for avatar conversations.

    This chain orchestrates the avatar's response generation using:
    - ChatPromptTemplate with system prompt + chat history + user input
    - LangChain's | operator for chain composition (prompt | llm | parser)
    - LangSmith @traceable for automatic tracing
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm
        self._output_parser = StrOutputParser()

    def _build_prompt(self) -> ChatPromptTemplate:
        """Build the chat prompt template.

        Returns:
            A ChatPromptTemplate with system, history, and human placeholders.
        """
        return ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
        ])

    @traceable(name="avatar_response", run_type="chain")
    async def invoke(
        self,
        request: ChatGenerateRequest,
        relevant_insights: list[str],
    ) -> str:
        """Generate avatar response with LangSmith tracing.

        Args:
            request: The chat generation request.
            relevant_insights: List of relevant insight strings from vector memory.

        Returns:
            The avatar's response as a string.
        """
        # Construir system prompt dinámico
        system_prompt = get_avatar_system_prompt(
            user_profile=request.user_profile,
            social_data=request.social_data,
            health_data=request.health_data,
            insights=relevant_insights,
        )

        # Construir la chain: prompt | llm | output_parser
        prompt = self._build_prompt()
        chain = prompt | self._llm | self._output_parser

        # Convertir historial a mensajes LangChain
        chat_history = self._convert_history(request.conversation_history)

        # Invocar con tracing automático
        response: str = await chain.ainvoke({
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "input": request.message,
        })

        return response

    @traceable(name="avatar_stream", run_type="chain")
    async def stream(
        self,
        request: ChatGenerateRequest,
        relevant_insights: list[str],
    ):
        """Stream avatar response chunks with LangSmith tracing.

        Args:
            request: The chat generation request.
            relevant_insights: List of relevant insight strings from vector memory.

        Yields:
            Response content chunks as they arrive from the LLM.
        """
        system_prompt = get_avatar_system_prompt(
            user_profile=request.user_profile,
            social_data=request.social_data,
            health_data=request.health_data,
            insights=relevant_insights,
        )

        prompt = self._build_prompt()
        chain = prompt | self._llm | self._output_parser

        chat_history = self._convert_history(request.conversation_history)

        async for chunk in chain.astream({
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "input": request.message,
        }):
            yield chunk

    def _convert_history(
        self,
        history: list[dict[str, str]],
    ) -> list[BaseMessage]:
        """Convert history dict list to LangChain message format.

        Args:
            history: List of message dicts with 'role' and 'content' keys.

        Returns:
            List of LangChain BaseMessage instances (last 20 messages).
        """
        messages: list[BaseMessage] = []
        for msg in history[-20:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        return messages
```

### 5.4 Prompt Templates

```python
# prompts/avatar_prompts.py
from typing import Optional

from app.models.schemas import UserProfile


def get_avatar_system_prompt(
    user_profile: UserProfile,
    social_data: Optional[dict[str, object]] = None,
    health_data: Optional[dict[str, object]] = None,
    insights: Optional[list[str]] = None,
) -> str:
    """Build dynamic system prompt for avatar.

    This function constructs a personalized system prompt that includes
    user profile data, social network data, health data, and previously
    extracted insights. The result is passed to ChatPromptTemplate as
    the system message variable.

    Args:
        user_profile: The user's profile data.
        social_data: Data from connected social networks.
        health_data: Health and activity data.
        insights: Relevant insight strings from vector memory.

    Returns:
        A formatted system prompt string.
    """
    # Formatear intereses
    interests_str = (
        ", ".join(user_profile.interests)
        if user_profile.interests
        else "No especificados"
    )

    # Sección de datos sociales
    social_section = ""
    if social_data and social_data.get("facebook"):
        fb = social_data["facebook"]
        if isinstance(fb, dict):
            likes = fb.get("likes")
            if isinstance(likes, list):
                social_section = (
                    f"\nDATOS DE FACEBOOK:\n"
                    f"- Páginas que le gustan: {', '.join(str(l) for l in likes[:10])}"
                )

    # Sección de datos de salud
    health_section = ""
    if health_data and health_data.get("steps"):
        health_section = (
            f"\nACTIVIDAD DE HOY:\n"
            f"- Pasos: {health_data.get('steps')}\n"
            f"- Promedio: {health_data.get('avg_steps', 'No disponible')}"
        )

    # Sección de insights
    insights_section = "- Aún no tienes suficiente información"
    if insights:
        insights_section = "\n".join(f"- {insight}" for insight in insights[:10])

    return f"""Eres {user_profile.avatar_name}, el avatar digital de {user_profile.display_name}.

SOBRE TI:
- No eres {user_profile.display_name}, pero estás hecho a partir de él/ella
- Tu rol es ser un compañero que lo conoce profundamente
- Hablas de forma cálida, cercana y natural
- Recuerdas cosas que te ha contado antes

PERFIL DE {user_profile.display_name}:
- Edad: {user_profile.age_range or "No especificado"}
- Intereses: {interests_str}
{social_section}
{health_section}

COSAS QUE SABES DE {user_profile.display_name}:
{insights_section}

INSTRUCCIONES:
1. Responde de forma conversacional y empática
2. Usa la información que conoces de forma natural, no la listes
3. Si mencionó algo importante antes, puedes recordárselo sutilmente
4. Haz preguntas para conocerlo mejor cuando sea apropiado
5. No seas invasivo, usa los datos con tacto
6. Nivel de conocimiento actual: {user_profile.knowledge_level}/5
7. Responde en el mismo idioma que el usuario"""


# prompts/insight_prompts.py
INSIGHT_EXTRACTION_TEMPLATE = """Analiza el siguiente mensaje del usuario y extrae insights \
sobre su personalidad, preferencias, historia personal, relaciones, metas o emociones.

Mensaje del usuario: {message}

Contexto previo del usuario:
{context}

Extrae solo insights que tengan alta confianza (>0.7). Si no hay insights claros, \
devuelve una lista vacía.

{format_instructions}
"""

SENTIMENT_ANALYSIS_TEMPLATE = """Analiza el sentimiento y la emoción principal del siguiente \
mensaje del usuario.

Mensaje: {message}

Determina:
1. El sentimiento general (positivo, negativo, neutro)
2. La emoción principal (alegría, tristeza, enojo, miedo, sorpresa, asco, neutral)
3. La intensidad de la emoción (0.0 a 1.0)

{format_instructions}
"""
```

### 5.5 Insight Extraction Chain

```python
# chains/insight_chain.py
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.prompts.insight_prompts import INSIGHT_EXTRACTION_TEMPLATE


class ExtractedInsight(BaseModel):
    """Schema for a single extracted insight (Pydantic output model)."""

    category: str = Field(
        description="Category: personal_history, preference, relationship, goal, emotion, health"
    )
    content: str = Field(description="The insight content in the user's language")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")


class ExtractedInsights(BaseModel):
    """List of extracted insights (Pydantic output model for PydanticOutputParser)."""

    insights: list[ExtractedInsight] = Field(default_factory=list)


class InsightExtractionChain:
    """LangChain chain for extracting insights from user messages.

    Uses PydanticOutputParser to get structured output from the LLM,
    ensuring each insight has a category, content, and confidence score.
    All invocations are traced via LangSmith @traceable.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm
        self._parser = PydanticOutputParser(pydantic_object=ExtractedInsights)

    @traceable(name="extract_insights", run_type="chain")
    async def invoke(
        self,
        message: str,
        context: str = "",
    ) -> list[ExtractedInsight]:
        """Extract insights from a user message.

        Args:
            message: The user's message to analyze.
            context: Previous context about the user (from vector memory).

        Returns:
            List of extracted insights with category, content, and confidence.
        """
        prompt = ChatPromptTemplate.from_template(INSIGHT_EXTRACTION_TEMPLATE)

        # Componer chain: prompt | llm | pydantic_parser
        chain = prompt | self._llm | self._parser

        result: ExtractedInsights = await chain.ainvoke({
            "message": message,
            "context": context,
            "format_instructions": self._parser.get_format_instructions(),
        })

        return result.insights
```

### 5.6 Sentiment Chain

```python
# chains/sentiment_chain.py
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.prompts.insight_prompts import SENTIMENT_ANALYSIS_TEMPLATE


class SentimentResult(BaseModel):
    """Schema for sentiment analysis result (Pydantic output model)."""

    sentiment: str = Field(description="Overall sentiment: positivo, negativo, neutro")
    primary_emotion: str = Field(
        description="Primary emotion: alegría, tristeza, enojo, miedo, sorpresa, asco, neutral"
    )
    intensity: float = Field(description="Emotion intensity from 0.0 to 1.0")


class SentimentChain:
    """LangChain chain for sentiment and emotion analysis.

    Uses PydanticOutputParser to get structured sentiment data.
    All invocations are traced via LangSmith @traceable.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm
        self._parser = PydanticOutputParser(pydantic_object=SentimentResult)

    @traceable(name="analyze_sentiment", run_type="chain")
    async def invoke(self, message: str) -> SentimentResult:
        """Analyze sentiment and primary emotion of a message.

        Args:
            message: The user's message to analyze.

        Returns:
            SentimentResult with sentiment, primary_emotion, and intensity.
        """
        prompt = ChatPromptTemplate.from_template(SENTIMENT_ANALYSIS_TEMPLATE)

        # Componer chain: prompt | llm | pydantic_parser
        chain = prompt | self._llm | self._parser

        result: SentimentResult = await chain.ainvoke({
            "message": message,
            "format_instructions": self._parser.get_format_instructions(),
        })

        return result
```

### 5.7 Vector Memory (pgvector via LangChain)

```python
# memory/vector_memory.py
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres.vectorstores import PGVector
from langsmith import traceable

from app.config.settings import Settings


class VectorMemory:
    """Vector store memory using pgvector via LangChain.

    Wraps LangChain's PGVector integration for storing and retrieving
    user insights using semantic similarity search. All operations
    are traced via LangSmith @traceable.
    """

    def __init__(
        self,
        embeddings: Embeddings,
        settings: Settings,
    ) -> None:
        self._embeddings = embeddings
        self._collection_name = "user_insights"

        self._vector_store = PGVector(
            embeddings=embeddings,
            collection_name=self._collection_name,
            connection=settings.database_url,
            use_jsonb=True,
        )

    @traceable(name="search_similar_insights", run_type="retriever")
    async def search_similar(
        self,
        query: str,
        user_id: str,
        k: int = 5,
    ) -> list[Document]:
        """Search for similar insights using vector similarity.

        Args:
            query: The search query (typically the user's message).
            user_id: Filter results to this user only.
            k: Number of results to return.

        Returns:
            List of LangChain Document objects sorted by similarity.
        """
        results: list[Document] = await self._vector_store.asimilarity_search(
            query=query,
            k=k,
            filter={"user_id": user_id},
        )
        return results

    @traceable(name="add_insight_to_memory")
    async def add_insight(
        self,
        user_id: str,
        content: str,
        category: str,
        confidence: float,
    ) -> str:
        """Add an insight to the vector store.

        Args:
            user_id: The user's ID.
            content: The insight text content.
            category: The insight category.
            confidence: Confidence score (0.0 to 1.0).

        Returns:
            The ID of the stored document.
        """
        doc = Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "category": category,
                "confidence": confidence,
            },
        )

        ids: list[str] = await self._vector_store.aadd_documents([doc])
        return ids[0]

    async def delete_user_insights(self, user_id: str) -> None:
        """Delete all insights for a user (GDPR compliance).

        Args:
            user_id: The user's ID.
        """
        await self._vector_store.adelete(filter={"user_id": user_id})

    async def get_insight_count(self, user_id: str) -> int:
        """Get the number of stored insights for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Number of stored insights.
        """
        docs: list[Document] = await self._vector_store.asimilarity_search(
            query="",
            k=1000,
            filter={"user_id": user_id},
        )
        return len(docs)
```

### 5.8 Conversation Memory

```python
# memory/conversation_memory.py
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class ConversationMemory:
    """Manages short-term conversation memory.

    Converts raw conversation history dicts into LangChain BaseMessage
    format, applying a sliding window to keep only recent messages.
    """

    DEFAULT_MAX_MESSAGES: int = 20

    def __init__(self, max_messages: int = DEFAULT_MAX_MESSAGES) -> None:
        self._max_messages = max_messages

    def convert_history(
        self,
        history: list[dict[str, str]],
    ) -> list[BaseMessage]:
        """Convert raw history to LangChain messages with windowing.

        Args:
            history: List of message dicts with 'role' and 'content' keys.

        Returns:
            List of LangChain BaseMessage instances, limited to max_messages.
        """
        messages: list[BaseMessage] = []
        for msg in history[-self._max_messages :]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        return messages
```

### 5.9 Combined Memory

```python
# memory/combined_memory.py
from typing import Optional

from langchain_core.documents import Document
from langsmith import traceable

from app.memory.conversation_memory import ConversationMemory
from app.memory.vector_memory import VectorMemory
from app.models.schemas import InsightCategory


class CombinedMemory:
    """Combines conversation memory with vector memory.

    The memory system has three layers:
    1. Short-term: Recent conversation (ConversationMemory, sliding window)
    2. Medium-term: Session summaries (future feature)
    3. Long-term: Extracted insights with semantic search (VectorMemory)
    """

    def __init__(
        self,
        conversation_memory: ConversationMemory,
        vector_memory: VectorMemory,
    ) -> None:
        self._conversation = conversation_memory
        self._vector = vector_memory

    @traceable(name="retrieve_combined_context", run_type="retriever")
    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        conversation_history: list[dict[str, str]],
        top_k: int = 5,
    ) -> dict[str, object]:
        """Retrieve combined context from all memory layers.

        Args:
            user_id: The user's ID.
            query: The current user message.
            conversation_history: Raw conversation history.
            top_k: Number of similar insights to retrieve.

        Returns:
            Dict with 'chat_history' (BaseMessage list) and
            'relevant_insights' (string list).
        """
        # Short-term: conversation buffer
        chat_history = self._conversation.convert_history(conversation_history)

        # Long-term: vector similarity search
        similar_docs: list[Document] = await self._vector.search_similar(
            query=query,
            user_id=user_id,
            k=top_k,
        )
        relevant_insights = [doc.page_content for doc in similar_docs]

        return {
            "chat_history": chat_history,
            "relevant_insights": relevant_insights,
        }

    async def get_user_memory_summary(
        self,
        user_id: str,
    ) -> dict[str, object]:
        """Get a summary of user's memory across all layers.

        Args:
            user_id: The user's ID.

        Returns:
            Summary including total insights and knowledge level.
        """
        insight_count = await self._vector.get_insight_count(user_id)

        return {
            "user_id": user_id,
            "total_insights": insight_count,
            "knowledge_level": self._calculate_knowledge_level(insight_count),
        }

    def _calculate_knowledge_level(self, count: int) -> int:
        """Calculate knowledge level based on insight count.

        Level 1: 0-5 insights
        Level 2: 6-15 insights
        Level 3: 16-30 insights
        Level 4: 31-50 insights
        Level 5: 50+ insights
        """
        if count <= 5:
            return 1
        elif count <= 15:
            return 2
        elif count <= 30:
            return 3
        elif count <= 50:
            return 4
        return 5

    async def delete_user_memory(self, user_id: str) -> None:
        """Delete all memory for a user (GDPR compliance).

        Args:
            user_id: The user's ID.
        """
        await self._vector.delete_user_insights(user_id)
```

### 5.10 Chat Service (Orquestador)

```python
# services/chat_service.py
import asyncio
from collections.abc import AsyncIterator
from typing import Optional

from langsmith import traceable

from app.chains.avatar_chain import AvatarChain
from app.chains.insight_chain import ExtractedInsight, InsightExtractionChain
from app.chains.sentiment_chain import SentimentChain
from app.memory.vector_memory import VectorMemory
from app.models.schemas import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    Insight,
    InsightCategory,
)


class ChatService:
    """Orchestrates chat generation using LangChain components.

    This service wires together:
    - AvatarChain for response generation
    - InsightExtractionChain for extracting user insights
    - SentimentChain for emotion detection
    - VectorMemory for semantic similarity search

    All operations are traced end-to-end via LangSmith.
    """

    def __init__(
        self,
        avatar_chain: AvatarChain,
        insight_chain: InsightExtractionChain,
        sentiment_chain: SentimentChain,
        vector_memory: VectorMemory,
    ) -> None:
        self._avatar_chain = avatar_chain
        self._insight_chain = insight_chain
        self._sentiment_chain = sentiment_chain
        self._vector_memory = vector_memory

    @traceable(name="generate_chat_response", run_type="chain")
    async def generate_response(
        self,
        request: ChatGenerateRequest,
    ) -> ChatGenerateResponse:
        """Generate avatar response with full LangSmith tracing.

        Orchestrates the entire flow:
        1. Parallel: search similar insights + analyze sentiment
        2. Generate avatar response via AvatarChain
        3. Extract new insights via InsightExtractionChain
        4. Store high-confidence insights in vector memory

        Args:
            request: The chat generation request.

        Returns:
            The generated response with emotion and insights metadata.
        """
        # 1. Paralelo: buscar insights similares + analizar sentimiento
        similar_docs, sentiment_result = await asyncio.gather(
            self._vector_memory.search_similar(
                query=request.message,
                user_id=request.user_id,
                k=5,
            ),
            self._sentiment_chain.invoke(request.message),
        )
        relevant_insights = [doc.page_content for doc in similar_docs]

        # 2. Generar respuesta del avatar
        response_text: str = await self._avatar_chain.invoke(
            request=request,
            relevant_insights=relevant_insights,
        )

        # 3. Extraer insights del mensaje del usuario
        new_extracted: list[ExtractedInsight] = await self._insight_chain.invoke(
            message=request.message,
            context="\n".join(relevant_insights),
        )

        # 4. Almacenar insights con confidence >= 0.7
        stored_insights: list[Insight] = []
        for extracted in new_extracted:
            if extracted.confidence >= 0.7:
                insight_id = await self._vector_memory.add_insight(
                    user_id=request.user_id,
                    content=extracted.content,
                    category=extracted.category,
                    confidence=extracted.confidence,
                )
                stored_insights.append(
                    Insight(
                        id=insight_id,
                        user_id=request.user_id,
                        category=InsightCategory(extracted.category),
                        content=extracted.content,
                        confidence=extracted.confidence,
                        source="conversation",
                        created_at=datetime.now(tz=timezone.utc),
                    )
                )

        return ChatGenerateResponse(
            response=response_text,
            emotion_detected=sentiment_result.primary_emotion,
            new_insights=stored_insights,
            tokens_used=0,  # LangSmith rastrea tokens automáticamente
        )

    @traceable(name="stream_chat_response", run_type="chain")
    async def stream_response(
        self,
        request: ChatGenerateRequest,
    ) -> AsyncIterator[str]:
        """Stream avatar response chunks with LangSmith tracing.

        Args:
            request: The chat generation request.

        Yields:
            Response content chunks as they arrive from the LLM.
        """
        similar_docs = await self._vector_memory.search_similar(
            query=request.message,
            user_id=request.user_id,
            k=5,
        )
        relevant_insights = [doc.page_content for doc in similar_docs]

        async for chunk in self._avatar_chain.stream(
            request=request,
            relevant_insights=relevant_insights,
        ):
            yield chunk
```

### 5.11 LangSmith Configuration

```python
# config/langsmith.py
import os
from functools import lru_cache
from typing import Optional

from langchain_core.tracers import LangChainTracer
from langsmith import Client

from app.config.settings import Settings


@lru_cache
def get_langsmith_client(settings: Settings) -> Optional[Client]:
    """Get LangSmith client if configured.

    Sets environment variables for LangChain auto-tracing and returns
    a LangSmith Client instance for programmatic access.

    Args:
        settings: Application settings with LangSmith configuration.

    Returns:
        A LangSmith Client or None if not configured.
    """
    if not settings.langsmith_api_key:
        return None

    # Configurar variables de entorno para auto-tracing de LangChain
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

    return Client(api_key=settings.langsmith_api_key)


def get_tracer(settings: Settings) -> Optional[LangChainTracer]:
    """Get LangChain tracer for manual tracing.

    Use this when you need to pass a tracer explicitly to a chain
    via the `callbacks` parameter.

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
```

### 5.12 Avatar Agent (Agente con Tools, opcional)

```python
# agents/avatar_agent.py
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langsmith import traceable

from app.memory.vector_memory import VectorMemory


@tool
async def search_user_memories(
    query: str,
    user_id: str,
    k: int = 3,
) -> str:
    """Search the user's stored memories and insights.

    Use this tool when the avatar needs to recall specific information
    about the user that was mentioned in previous conversations.

    Args:
        query: What to search for in the user's memories.
        user_id: The user's unique identifier.
        k: Number of results to return.

    Returns:
        A formatted string of relevant memories.
    """
    # NOTE: In practice, vector_memory is injected via closure or class
    # This is a simplified example showing the tool interface
    return f"Searched for: {query} (user: {user_id}, top {k})"


class AvatarAgent:
    """LangChain Agent for advanced avatar interactions.

    Use this when the avatar needs tool-calling capabilities
    (e.g., searching memories on-demand, looking up health data).
    For simple Q&A, prefer AvatarChain instead.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        vector_memory: VectorMemory,
    ) -> None:
        self._llm = llm
        self._vector_memory = vector_memory
        self._tools = [search_user_memories]

    @traceable(name="avatar_agent_invoke", run_type="chain")
    async def invoke(
        self,
        user_id: str,
        message: str,
        system_prompt: str,
    ) -> str:
        """Invoke the avatar agent with tool access.

        Args:
            user_id: The user's ID.
            message: The user's message.
            system_prompt: The constructed system prompt.

        Returns:
            The agent's response string.
        """
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self._llm, self._tools, prompt)
        executor = AgentExecutor(agent=agent, tools=self._tools, verbose=False)

        result = await executor.ainvoke({
            "input": message,
            "chat_history": [],
        })

        return str(result.get("output", ""))
```

---

## 6. Base de Datos (pgvector)

### 6.1 SQLAlchemy Models

```python
# models/database.py
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class InsightModel(Base):
    """SQLAlchemy model for insights."""

    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),  # OpenAI embedding dimension
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Index for vector similarity search
    __table_args__ = (
        Index(
            "ix_insights_embedding",
            embedding,
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

### 6.2 Vector Store

```python
# embeddings/vector_store.py
from typing import Optional, Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import InsightModel
from app.models.schemas import Insight, InsightCategory


class VectorStore:
    """Vector store for semantic search using pgvector.

    This is the low-level SQLAlchemy-based vector store.
    For LangChain integration, prefer using memory/vector_memory.py
    which wraps LangChain's PGVector.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        user_id: str,
        embedding: list[float],
        top_k: int = 5,
        categories: Optional[list[InsightCategory]] = None,
    ) -> list[Insight]:
        """Search for similar insights using cosine similarity.

        Args:
            user_id: Filter by user ID.
            embedding: Query embedding vector.
            top_k: Number of results to return.
            categories: Optional category filter.

        Returns:
            List of insights sorted by similarity.
        """
        query = (
            select(InsightModel)
            .where(InsightModel.user_id == user_id)
            .where(InsightModel.embedding.isnot(None))
            .order_by(InsightModel.embedding.cosine_distance(embedding))
            .limit(top_k)
        )

        if categories:
            category_values = [c.value for c in categories]
            query = query.where(InsightModel.category.in_(category_values))

        result = await self._session.execute(query)
        rows = result.scalars().all()

        return [self._to_insight(row) for row in rows]

    async def delete_user_vectors(self, user_id: str) -> int:
        """Delete all vectors for a user.

        Args:
            user_id: The user's ID.

        Returns:
            Number of deleted records.
        """
        result = await self._session.execute(
            delete(InsightModel).where(InsightModel.user_id == user_id)
        )
        await self._session.commit()
        return result.rowcount or 0

    def _to_insight(self, model: InsightModel) -> Insight:
        """Convert database model to schema."""
        return Insight(
            id=model.id,
            user_id=model.user_id,
            category=InsightCategory(model.category),
            content=model.content,
            confidence=model.confidence,
            source=model.source,
            created_at=model.created_at,
        )
```

---

## 7. API Endpoints a Implementar

### Prioridad 1 (Semana 1)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check del servicio |
| POST | `/internal/chat/generate` | Generar respuesta del avatar |

### Prioridad 2 (Semana 2)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/internal/chat/stream` | Streaming de respuesta |
| GET | `/internal/memory/{user_id}` | Obtener memoria del usuario |
| POST | `/internal/memory/{user_id}/insights` | Agregar insight manual |
| DELETE | `/internal/memory/{user_id}` | Borrar memoria (GDPR) |
| POST | `/internal/insights/extract` | Extraer insights de texto |
| GET | `/internal/insights/search` | Búsqueda semántica |

### Prioridad 3 (Semana 3)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/internal/embeddings/generate` | Generar embedding |
| POST | `/internal/analysis/sentiment` | Análisis de sentimiento |

---

## 8. Testing

### Unit Tests

```python
# tests/unit/test_avatar_chain.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.chains.avatar_chain import AvatarChain
from app.models.schemas import ChatGenerateRequest, UserProfile


class TestAvatarChain:
    """Tests for AvatarChain."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        llm = MagicMock(spec=BaseChatModel)
        llm.ainvoke = AsyncMock(return_value=AIMessage(content="Hola, ¿cómo estás?"))
        return llm

    @pytest.fixture
    def chain(self, mock_llm: MagicMock) -> AvatarChain:
        return AvatarChain(llm=mock_llm)

    @pytest.fixture
    def user_profile(self) -> UserProfile:
        return UserProfile(
            display_name="Juan",
            avatar_name="Juanito",
            age_range="25_34",
            interests=["tecnología", "fútbol"],
            knowledge_level=2,
        )

    @pytest.fixture
    def chat_request(self, user_profile: UserProfile) -> ChatGenerateRequest:
        return ChatGenerateRequest(
            user_id="test-user-123",
            message="Hola, ¿cómo estás?",
            conversation_id="conv-123",
            user_profile=user_profile,
            conversation_history=[],
        )

    def test_build_prompt(self, chain: AvatarChain) -> None:
        """Test that prompt template has correct message placeholders."""
        prompt = chain._build_prompt()
        input_vars = prompt.input_variables

        assert "system_prompt" in input_vars
        assert "input" in input_vars

    def test_convert_history_empty(self, chain: AvatarChain) -> None:
        """Test converting empty history."""
        messages = chain._convert_history([])
        assert messages == []

    def test_convert_history_mixed(self, chain: AvatarChain) -> None:
        """Test converting mixed user/assistant history."""
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿Cómo estás?"},
            {"role": "user", "content": "Bien, gracias"},
        ]
        messages = chain._convert_history(history)

        assert len(messages) == 3
        assert messages[0].content == "Hola"
        assert messages[1].content == "¡Hola! ¿Cómo estás?"
        assert messages[2].content == "Bien, gracias"

    def test_convert_history_truncates(self, chain: AvatarChain) -> None:
        """Test that history is truncated to last 20 messages."""
        history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(30)
        ]
        messages = chain._convert_history(history)
        assert len(messages) == 20


# tests/unit/test_insight_chain.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.chains.insight_chain import (
    ExtractedInsight,
    ExtractedInsights,
    InsightExtractionChain,
)


class TestInsightExtractionChain:
    """Tests for InsightExtractionChain."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def chain(self, mock_llm: MagicMock) -> InsightExtractionChain:
        return InsightExtractionChain(llm=mock_llm)

    def test_parser_format_instructions(
        self, chain: InsightExtractionChain
    ) -> None:
        """Test that parser produces valid format instructions."""
        instructions = chain._parser.get_format_instructions()
        assert "category" in instructions
        assert "content" in instructions
        assert "confidence" in instructions


# tests/unit/test_sentiment_chain.py
import pytest
from unittest.mock import MagicMock

from app.chains.sentiment_chain import SentimentChain, SentimentResult


class TestSentimentChain:
    """Tests for SentimentChain."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def chain(self, mock_llm: MagicMock) -> SentimentChain:
        return SentimentChain(llm=mock_llm)

    def test_parser_format_instructions(
        self, chain: SentimentChain
    ) -> None:
        """Test that parser produces valid format instructions."""
        instructions = chain._parser.get_format_instructions()
        assert "sentiment" in instructions
        assert "primary_emotion" in instructions
        assert "intensity" in instructions


# tests/unit/test_vector_memory.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.documents import Document

from app.memory.vector_memory import VectorMemory


class TestVectorMemory:
    """Tests for VectorMemory."""

    @pytest.fixture
    def mock_embeddings(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://test:test@localhost/test"
        return settings

    def test_add_insight_creates_document(self) -> None:
        """Test that add_insight creates a properly formatted Document."""
        doc = Document(
            page_content="Le gusta el café",
            metadata={
                "user_id": "user-123",
                "category": "preference",
                "confidence": 0.9,
            },
        )

        assert doc.page_content == "Le gusta el café"
        assert doc.metadata["user_id"] == "user-123"
        assert doc.metadata["category"] == "preference"
        assert doc.metadata["confidence"] == 0.9
```

### Integration Tests

```python
# tests/integration/test_chat_endpoint.py
import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
class TestChatEndpoint:
    """Integration tests for chat endpoint."""

    @pytest.fixture
    async def client(self) -> AsyncClient:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client

    async def test_generate_response(self, client: AsyncClient) -> None:
        """Test generating a chat response."""
        request_data = {
            "user_id": "test-user-123",
            "message": "Hola, ¿cómo estás?",
            "conversation_id": "conv-123",
            "user_profile": {
                "display_name": "Test User",
                "avatar_name": "Testy",
                "interests": ["testing"],
                "knowledge_level": 1,
            },
            "conversation_history": [],
        }

        response = await client.post(
            "/internal/chat/generate",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "tokens_used" in data
        assert data["tokens_used"] >= 0

    async def test_health_check(self, client: AsyncClient) -> None:
        """Test health check endpoint."""
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

---

## 9. Comandos Útiles

```bash
# Desarrollo
uvicorn app.main:app --reload --port 8000

# Con hot reload y logs detallados
uvicorn app.main:app --reload --port 8000 --log-level debug

# Type checking
pyright app/

# Linting
ruff check app/
ruff check app/ --fix  # Auto-fix

# Formatting
black app/
isort app/

# Testing
pytest                          # Todos los tests
pytest tests/unit/              # Solo unit tests
pytest tests/integration/       # Solo integration tests
pytest -v --cov=app             # Con coverage
pytest -x                       # Parar en primer error

# Base de datos
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# Docker
docker build -t golive-ai-agents .
docker run -p 8000:8000 golive-ai-agents
```

---

## 10. Variables de Entorno

```bash
# .env.example

# Environment
ENVIRONMENT=development
DEBUG=true

# LangSmith (OBLIGATORIO para observabilidad)
LANGSMITH_API_KEY=lsv2_pt_your-langsmith-api-key
LANGSMITH_PROJECT=golive-ai-agents
LANGCHAIN_TRACING_V2=true

# Database
DATABASE_URL=postgresql+asyncpg://golive:password@localhost:5432/golive

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4-turbo-preview

# Anthropic (alternativo)
ANTHROPIC_API_KEY=sk-ant-your-api-key
ANTHROPIC_MODEL=claude-3-opus-20240229

# LLM Configuration
LLM_PROVIDER=openai  # openai | anthropic
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Embeddings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Logging
LOG_LEVEL=INFO
```

---

## 11. Checklist de Calidad

Antes de cada PR, verificar:

- [ ] `pyright app/` pasa sin errores (strict mode)
- [ ] `ruff check app/` pasa sin errores
- [ ] `black --check app/` pasa sin cambios
- [ ] `pytest` pasa todos los tests
- [ ] Todos los tipos están anotados explícitamente
- [ ] Los docstrings siguen el formato Google
- [ ] No hay `# type: ignore` innecesarios
- [ ] No hay secrets hardcodeados
- [ ] Los endpoints tienen response_model definido
- [ ] Los errores usan excepciones personalizadas
- [ ] Las operaciones async independientes usan `asyncio.gather`
- [ ] Todas las chains tienen decorador `@traceable`
- [ ] Las trazas de LangSmith aparecen en el dashboard
- [ ] Los prompts usan `ChatPromptTemplate` (no strings crudos)
- [ ] Las salidas estructuradas usan `PydanticOutputParser`
- [ ] Los LLMs se instancian via factory (`get_llm`) no clientes directos

---

## 12. Comunicación con API-Backend

### Contrato de API

El `api-backend` te enviará requests con este formato:

```json
{
  "user_id": "uuid-del-usuario",
  "message": "Mensaje del usuario",
  "conversation_id": "uuid-de-la-conversacion",
  "user_profile": {
    "display_name": "Juan Pérez",
    "avatar_name": "Juanito",
    "age_range": "25_34",
    "interests": ["tecnología", "deportes"],
    "knowledge_level": 2
  },
  "social_data": {
    "facebook": {
      "likes": ["FC Barcelona", "TechCrunch"]
    }
  },
  "health_data": {
    "steps": 5000,
    "avg_steps": 8000
  },
  "conversation_history": [
    {"role": "user", "content": "Hola"},
    {"role": "assistant", "content": "¡Hola! ¿Cómo estás?"}
  ]
}
```

Y debes responder con:

```json
{
  "response": "Respuesta del avatar",
  "emotion_detected": "neutral",
  "new_insights": [
    {
      "id": "generated-uuid",
      "category": "preference",
      "content": "Le interesa la tecnología",
      "confidence": 0.85
    }
  ],
  "suggested_followup": null,
  "tokens_used": 150
}
```
