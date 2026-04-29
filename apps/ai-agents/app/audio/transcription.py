"""Audio transcription provider abstraction.

v1 ships an OpenAI provider; the dispatcher reads
``AUDIO_TRANSCRIPTION_PROVIDER`` from settings so we can swap to a
self-hosted faster-whisper later without changing call sites.

Default model: ``gpt-4o-mini-transcribe`` (~$0.003/min, text-only).
``whisper-1`` returns native segments; the gpt-4o family does not yet,
so when the chosen model is anything other than ``whisper-1`` we return
an empty segments list. The chunk transcript still fills `transcript`
on the Rails side.
"""

import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str


@dataclass
class Transcription:
    text: str
    language: str | None
    segments: list[TranscriptionSegment] = field(default_factory=list)
    model: str | None = None
    provider: str | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "segments": [s.__dict__ for s in self.segments],
            "model": self.model,
            "provider": self.provider,
        }


async def transcribe_bytes(
    audio: bytes,
    *,
    settings: Settings,
    filename: str = "chunk.m4a",
    mime: str = "audio/m4a",
    language: str | None = None,
) -> Transcription:
    """Transcribe an in-memory audio buffer.

    Args:
        audio: Raw bytes of the audio file (m4a/aac/mp3/wav).
        settings: App settings (provides API key + model selection).
        filename: Used by the OpenAI client to pick a content type.
        mime: MIME hint passed alongside the bytes.
        language: ISO 639-1 code; improves accuracy on Spanish, etc.

    Returns:
        ``Transcription`` with text and (optionally) segments.

    Raises:
        ValueError if the configured provider is unknown.
    """
    provider = (settings.audio_transcription_provider or "openai").lower()
    if provider == "openai":
        return await _transcribe_openai(
            audio,
            settings=settings,
            filename=filename,
            mime=mime,
            language=language,
        )
    raise ValueError(f"Unknown AUDIO_TRANSCRIPTION_PROVIDER: {provider!r}")


async def _transcribe_openai(
    audio: bytes,
    *,
    settings: Settings,
    filename: str,
    mime: str,
    language: str | None,
) -> Transcription:
    api_key = settings.openai_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot transcribe.")

    model = settings.audio_transcription_model
    client = AsyncOpenAI(api_key=api_key)

    extra: dict = {}
    if model == "whisper-1":
        extra["response_format"] = "verbose_json"
    if language:
        extra["language"] = language

    logger.info("Transcribing %d bytes via %s/%s lang=%s", len(audio), "openai", model, language)
    resp = await client.audio.transcriptions.create(
        model=model,
        file=(filename, audio, mime),
        **extra,
    )

    text = getattr(resp, "text", "") or ""
    segments: list[TranscriptionSegment] = []
    resp_lang = getattr(resp, "language", None)

    if model == "whisper-1":
        raw_segments = getattr(resp, "segments", None) or []
        for s in raw_segments:
            try:
                segments.append(TranscriptionSegment(
                    start=float(getattr(s, "start", 0.0)),
                    end=float(getattr(s, "end", 0.0)),
                    text=str(getattr(s, "text", "")),
                ))
            except Exception:  # noqa: BLE001
                # tolerate unexpected segment shapes; the text alone is enough
                continue

    return Transcription(
        text=text,
        language=resp_lang or language,
        segments=segments,
        model=model,
        provider="openai",
    )
