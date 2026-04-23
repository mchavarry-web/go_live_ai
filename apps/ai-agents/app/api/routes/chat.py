"""Chat endpoints for avatar response generation.

Provides endpoints for generating and streaming avatar responses.
Called exclusively by api-backend via internal HTTP requests.
All LLM calls are traced via LangSmith.

Endpoints:
    POST /internal/chat/generate - Generate a complete avatar response.
    POST /internal/chat/stream   - Stream avatar response via SSE.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from starlette.responses import StreamingResponse

from app.api.deps import DbSessionDep, LLMDep, SettingsDep
from app.llm.providers import get_embeddings
from app.models.schemas import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    ProactiveGenerateRequest,
    ProactiveGenerateResponse,
)
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/chat", tags=["Chat"])


@router.post(
    "/generate",
    response_model=ChatGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate avatar response",
    description=(
        "Generate a personalized response from the user's avatar using "
        "LangChain chains. Includes insight extraction and memory retrieval."
    ),
)
async def generate_chat_response(
    request: ChatGenerateRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> ChatGenerateResponse:
    """Generate a chat response from the avatar.

    This endpoint is called by api-backend when a user sends a message.
    It orchestrates the response generation process including memory
    retrieval, prompt building, LLM invocation, and insight extraction.

    Args:
        request: The chat generation request with message and context.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        ChatGenerateResponse with the avatar's reply and metadata.

    Raises:
        HTTPException: If response generation fails.
    """
    try:
        embeddings = get_embeddings(settings)
        service = ChatService(llm=llm, settings=settings, embeddings=embeddings)
        response = await service.generate_response(request, session=session)
        return response
    except ValueError as exc:
        logger.error("Validation error in chat generation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid request data: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error in chat generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate avatar response. Please try again.",
        ) from exc


@router.post(
    "/stream",
    summary="Stream avatar response",
    description="Stream a response from the avatar in real-time using LangChain streaming via SSE.",
)
async def stream_chat_response(
    request: ChatGenerateRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> StreamingResponse:
    """Stream a chat response for real-time display.

    Uses LangChain's ``astream`` to yield response chunks as they
    arrive from the LLM via Server-Sent Events (SSE).

    Args:
        request: The chat generation request with message and context.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        A StreamingResponse with SSE-formatted token chunks.

    Raises:
        HTTPException: If stream setup fails.
    """
    try:
        embeddings = get_embeddings(settings)
        service = ChatService(llm=llm, settings=settings, embeddings=embeddings)
        return StreamingResponse(
            content=service.generate_stream(request, session=session),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except ValueError as exc:
        logger.error("Validation error in chat streaming: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid request data: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error setting up chat stream")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start avatar response stream.",
        ) from exc


@router.post(
    "/proactive-generate",
    response_model=ProactiveGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate proactive avatar greeting",
    description=(
        "Generate a short, personalized proactive greeting from the avatar "
        "when the user returns to the app after inactivity. "
        "The skill_id determines the type of content generated."
    ),
)
async def generate_proactive_greeting(
    request: ProactiveGenerateRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> ProactiveGenerateResponse:
    """Generate a proactive avatar greeting.

    Called by api-backend when the user opens the app after inactivity.
    Unlike the regular chat endpoint, the avatar speaks first based on
    the selected proactive skill.

    Args:
        request: The proactive greeting request with skill and user context.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        ProactiveGenerateResponse with the avatar's greeting and metadata.

    Raises:
        HTTPException: If greeting generation fails.
    """
    try:
        embeddings = get_embeddings(settings)
        service = ChatService(llm=llm, settings=settings, embeddings=embeddings)
        return await service.generate_proactive_greeting(request, session=session)
    except ValueError as exc:
        logger.error("Validation error in proactive greeting generation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid request data: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error in proactive greeting generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate proactive greeting. Please try again.",
        ) from exc
