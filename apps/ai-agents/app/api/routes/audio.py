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
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import DbSessionDep, LLMDep, SettingsDep
from app.audio.synthesis import synthesize_text
from app.audio.transcription import TranscriptionError, transcribe_bytes
from app.chains.insight_chain import InsightExtractionChain
from app.llm.providers import get_embeddings
from app.models.schemas import Insight
from app.repositories.audio_transcript_repository import AudioTranscriptRepository
from app.services.event_service import EventService
from app.services.memory_service import MemoryService
from app.services.transcript_chunker import chunk_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/audio", tags=["Audio"])


# ── Schemas ─────────────────────────────────────────────────────────────


class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None
    segments: list[dict] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    # Failure discriminator. ``None`` on success; on failure ``text`` is ""
    # and this is one of "quota" | "unsupported_format" | "provider_error".
    # Additive — existing callers that only read ``text`` keep working.
    error: str | None = None


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5_000)
    voice: str | None = Field(
        default=None,
        max_length=40,
        description="Override the configured default voice (e.g. nova, alloy).",
    )
    audio_format: str = Field(
        default="mp3",
        max_length=8,
        description="Output container; one of mp3/opus/aac/flac/wav.",
    )


class AudioInsightsRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    transcript: str = Field(..., min_length=1, max_length=20_000)
    source: str = Field(..., min_length=1, max_length=120)
    context: str = Field(default="", max_length=2_000)
    timezone: str | None = Field(
        default=None,
        max_length=50,
        description="IANA tz of the user; falls back to America/Lima.",
    )
    recorded_at: datetime | None = Field(
        default=None,
        description=(
            "UTC timestamp when the chunk was recorded. Used as RELATIVE_BASE "
            "for event-extraction date resolution. Falls back to now()."
        ),
    )
    audio_chunk_id: str | None = Field(
        default=None,
        max_length=36,
        description="Rails AudioChunk id for traceability on extracted events.",
    )
    audio_session_id: str | None = Field(
        default=None,
        max_length=36,
        description=(
            "Rails AudioSession id; persisted on transcript chunks so a "
            "session-level wipe can target them without a join."
        ),
    )


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
    import time

    t0 = time.perf_counter()
    try:
        raw = await audio.read()
        logger.info(
            "audio.transcribe: received user_id=%s filename=%s mime=%s bytes=%d lang=%s",
            user_id,
            audio.filename,
            audio.content_type,
            len(raw),
            language,
        )
        if not raw:
            logger.warning("audio.transcribe: empty payload user_id=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty audio payload.",
            )

        t_provider = time.perf_counter()
        result = await transcribe_bytes(
            raw,
            settings=settings,
            filename=audio.filename or "chunk.m4a",
            mime=audio.content_type or "audio/m4a",
            language=language or None,
        )
        provider_ms = (time.perf_counter() - t_provider) * 1000
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "audio.transcribe: done user_id=%s bytes=%d chars=%d segments=%d "
            "model=%s provider=%s provider_ms=%d total_ms=%d",
            user_id,
            len(raw),
            len(result.text),
            len(result.segments),
            result.model,
            result.provider,
            int(provider_ms),
            int(total_ms),
        )
        return TranscribeResponse(
            text=result.text,
            language=result.language,
            segments=[s.__dict__ for s in result.segments],
            model=result.model,
            provider=result.provider,
            error=None,
        )
    except HTTPException:
        raise
    except TranscriptionError as exc:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "audio.transcribe: provider failure user_id=%s after %dms kind=%s msg=%s",
            user_id,
            int(total_ms),
            exc.kind,
            str(exc),
        )
        return TranscribeResponse(text="", error=exc.kind)
    except Exception as exc:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "audio.transcribe: failed user_id=%s after %dms class=%s msg=%s",
            user_id,
            int(total_ms),
            exc.__class__.__name__,
            str(exc),
        )
        return TranscribeResponse(text="", error="provider_error")


@router.post(
    "/synthesize",
    summary="Synthesize speech from text",
    description=(
        "Render text as spoken audio using the configured TTS provider "
        "(default: OpenAI tts-1 / nova). Returns the raw audio bytes "
        "so Rails can attach them to a Message via Shrine."
    ),
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def synthesize(
    request: SynthesizeRequest,
    settings: SettingsDep,
) -> Response:
    """Text in, audio bytes out. Stateless."""
    import time

    t0 = time.perf_counter()
    logger.info(
        "audio.synthesize: received chars=%d voice=%s fmt=%s",
        len(request.text), request.voice, request.audio_format,
    )
    try:
        result = await synthesize_text(
            request.text,
            settings=settings,
            voice=request.voice,
            audio_format=request.audio_format,
        )
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "audio.synthesize: done chars=%d bytes=%d voice=%s model=%s total_ms=%d",
            len(request.text), len(result.audio), result.voice, result.model, int(total_ms),
        )
        return Response(
            content=result.audio,
            media_type=result.mime,
            headers={
                "X-Audio-Voice":    result.voice or "",
                "X-Audio-Model":    result.model or "",
                "X-Audio-Provider": result.provider or "",
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "audio.synthesize: failed after %dms class=%s msg=%s",
            int(total_ms), exc.__class__.__name__, str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audio synthesis failed: {exc.__class__.__name__}",
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
    import time

    t0 = time.perf_counter()
    logger.info(
        "audio.insights: received user_id=%s source=%s transcript_chars=%d context_chars=%d",
        request.user_id,
        request.source,
        len(request.transcript),
        len(request.context),
    )
    try:
        import asyncio
        from datetime import UTC, datetime as _dt

        chain = InsightExtractionChain(llm=llm)
        event_service = EventService(session=session)

        # Phase 14: chunk + embed the transcript in parallel with insight
        # extraction. Pure CPU + one batched embedding call; cheap.
        async def _persist_transcript_chunks() -> int:
            if not request.audio_chunk_id or not request.audio_session_id:
                # Old Rails clients that don't pass identifiers can still
                # produce insights/events but won't get retrievable chunks
                # (we'd have nowhere to scope them).
                return 0
            windows = chunk_transcript(request.transcript)
            if not windows:
                return 0
            embeddings_provider = get_embeddings(settings)
            try:
                vectors = await embeddings_provider.aembed_documents(windows)
            except Exception:
                logger.exception(
                    "audio.transcript_chunks: embedding failed user_id=%s — skipping pool",
                    request.user_id,
                )
                return 0
            recorded_at = request.recorded_at or _dt.now(UTC)
            repo = AudioTranscriptRepository(session)
            return await repo.bulk_create(
                user_id=request.user_id,
                audio_chunk_id=request.audio_chunk_id,
                audio_session_id=request.audio_session_id,
                recorded_at=recorded_at,
                windows=windows,
                embeddings=list(vectors),
            )

        t_extract = time.perf_counter()
        extracted, stored_events, stored_chunks = await asyncio.gather(
            chain.extract(message=request.transcript, context=request.context),
            event_service.extract_and_store_from_text(
                llm=llm,
                user_id=request.user_id,
                text=request.transcript,
                source=request.source,
                timezone=request.timezone,
                anchor_at=request.recorded_at,
                source_message_id=request.audio_chunk_id,
            ),
            _persist_transcript_chunks(),
            return_exceptions=False,
        )
        extract_ms = (time.perf_counter() - t_extract) * 1000

        if not extracted:
            logger.info(
                "audio.insights: no insights produced user_id=%s source=%s "
                "events=%d transcript_chunks=%d extract_ms=%d",
                request.user_id,
                request.source,
                len(stored_events),
                stored_chunks,
                int(extract_ms),
            )
            return {
                "insights": [],
                "stored": 0,
                "events": len(stored_events),
                "transcript_chunks": stored_chunks,
            }

        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        insight_dicts = [
            {"category": ins.category, "content": ins.content, "confidence": ins.confidence}
            for ins in extracted
        ]

        t_store = time.perf_counter()
        stored = await memory_service.store_insights(
            user_id=request.user_id,
            insights=insight_dicts,
            source=request.source,
        )
        store_ms = (time.perf_counter() - t_store) * 1000

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
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "audio.insights: done user_id=%s source=%s extracted=%d stored=%d "
            "events=%d transcript_chunks=%d extract_ms=%d store_ms=%d total_ms=%d",
            request.user_id,
            request.source,
            len(extracted),
            len(stored),
            len(stored_events),
            stored_chunks,
            int(extract_ms),
            int(store_ms),
            int(total_ms),
        )
        return {
            "insights": [ins.model_dump() for ins in stored_insights],
            "stored": len(stored),
            "events": len(stored_events),
            "transcript_chunks": stored_chunks,
            "source": request.source,
        }

    except Exception as exc:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "audio.insights: failed user_id=%s source=%s after %dms class=%s msg=%s",
            request.user_id,
            request.source,
            int(total_ms),
            exc.__class__.__name__,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Audio insight extraction failed: {exc.__class__.__name__}",
        ) from exc
