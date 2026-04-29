"""Audio training endpoints.

Two operations sit behind these routes:

    POST /internal/audio/transcribe
        Multipart audio bytes → transcript text + (optional) segments.
        Stateless — nothing is persisted by this endpoint.

    POST /internal/audio/extract_insights
        Transcript text + source label → insights.
        Reuses the existing InsightExtractionChain so audio-derived insights
        share the chat-derived schema (personal_history / preference /
        relationship / goal / emotion / health). Persisted with the caller's
        source string (typically "audio:<session_id>").

Phase 2 will add ``/voice_print`` and ``/identify`` endpoints alongside.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import DbSessionDep, LLMDep, SettingsDep
from app.audio.transcription import transcribe_bytes
from app.chains.insight_chain import InsightExtractionChain
from app.llm.providers import get_embeddings
from app.models.schemas import Insight
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/audio", tags=["Audio"])


# ── Schemas ─────────────────────────────────────────────────────────────


class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None
    segments: list[dict] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None


class AudioInsightsRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    transcript: str = Field(..., min_length=1, max_length=20_000)
    source: str = Field(..., min_length=1, max_length=120)
    context: str = Field(default="", max_length=2_000)


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Transcribe an audio chunk",
    description=(
        "Accepts a multipart audio file (m4a/aac/mp3/wav) plus optional "
        "language hint and returns the transcript. Bytes are sent directly "
        "to the configured provider (default: OpenAI gpt-4o-mini-transcribe) "
        "and never persisted by this service."
    ),
)
async def transcribe(
    settings: SettingsDep,
    audio: Annotated[UploadFile, File(...)],
    user_id: Annotated[str, Form(...)],
    language: Annotated[str | None, Form()] = None,
) -> TranscribeResponse:
    """Multipart audio in, transcript out. Stateless."""
    try:
        raw = await audio.read()
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty audio payload.",
            )

        result = await transcribe_bytes(
            raw,
            settings=settings,
            filename=audio.filename or "chunk.m4a",
            mime=audio.content_type or "audio/m4a",
            language=language or None,
        )
        logger.info(
            "Transcribed audio: user_id=%s bytes=%d chars=%d segments=%d model=%s",
            user_id, len(raw), len(result.text), len(result.segments), result.model,
        )
        return TranscribeResponse(
            text=result.text,
            language=result.language,
            segments=[s.__dict__ for s in result.segments],
            model=result.model,
            provider=result.provider,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Audio transcription failed: user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio transcription failed.",
        ) from exc


@router.post(
    "/extract_insights",
    summary="Extract insights from an audio transcript",
    description=(
        "Runs the standard InsightExtractionChain over a transcript and "
        "stores the resulting insights tagged with the caller's source "
        "(typically 'audio:<session_id>') so the user can wipe them in bulk."
    ),
)
async def extract_audio_insights(
    request: AudioInsightsRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Transcript → insights tagged ``source``."""
    try:
        chain = InsightExtractionChain(llm=llm)
        extracted = await chain.extract(
            message=request.transcript,
            context=request.context,
        )

        if not extracted:
            return {"insights": [], "stored": 0}

        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        insight_dicts = [
            {"category": ins.category, "content": ins.content, "confidence": ins.confidence}
            for ins in extracted
        ]

        stored = await memory_service.store_insights(
            user_id=request.user_id,
            insights=insight_dicts,
            source=request.source,
        )

        stored_insights = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in stored
        ]
        return {
            "insights": [ins.model_dump() for ins in stored_insights],
            "stored": len(stored),
            "source": request.source,
        }

    except Exception as exc:
        logger.exception(
            "Audio insight extraction failed: user_id=%s source=%s",
            request.user_id, request.source,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio insight extraction failed.",
        ) from exc
