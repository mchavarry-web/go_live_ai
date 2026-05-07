"""Audio synthesis (text-to-speech) provider abstraction.

Mirrors transcription.py's shape: a thin dispatcher reads
``AUDIO_TTS_PROVIDER`` from settings so we can swap providers later
without changing call sites. v1 ships an OpenAI provider only.

Default model: ``tts-1`` (~$15/1M chars, mp3 out).
"""

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config.settings import Settings

logger = logging.getLogger(__name__)

# OpenAI hard cap; we trim input above this so the call doesn't 400.
OPENAI_TTS_INPUT_LIMIT = 4096


@dataclass
class Synthesis:
    audio: bytes
    mime: str
    model: str | None = None
    provider: str | None = None
    voice: str | None = None


async def synthesize_text(
    text: str,
    *,
    settings: Settings,
    voice: str | None = None,
    audio_format: str = "mp3",
) -> Synthesis:
    """Render ``text`` to spoken audio bytes.

    Args:
        text: The text to speak. Empty/whitespace raises ValueError.
        settings: App settings (provides API key, model, default voice).
        voice: Override the configured default voice (alloy / echo / fable /
            onyx / nova / shimmer for OpenAI tts-1).
        audio_format: Container/codec — ``mp3`` (default), ``opus``, ``aac``,
            ``flac``, or ``wav``.

    Returns:
        ``Synthesis`` carrying the raw audio bytes plus metadata.

    Raises:
        ValueError: Empty input or unknown provider.
        RuntimeError: Provider misconfigured (e.g. missing API key).
    """
    if not text or not text.strip():
        raise ValueError("Cannot synthesize empty text.")

    provider = (settings.audio_tts_provider or "openai").lower()
    if provider == "openai":
        return await _synthesize_openai(
            text,
            settings=settings,
            voice=voice or settings.audio_tts_voice,
            audio_format=audio_format,
        )
    raise ValueError(f"Unknown AUDIO_TTS_PROVIDER: {provider!r}")


async def _synthesize_openai(
    text: str,
    *,
    settings: Settings,
    voice: str,
    audio_format: str,
) -> Synthesis:
    import time

    api_key = settings.openai_api_key.get_secret_value()
    if not api_key:
        logger.error("audio.tts.openai: OPENAI_API_KEY is not set")
        raise RuntimeError("OPENAI_API_KEY is not set; cannot synthesize.")

    model = settings.audio_tts_model
    client = AsyncOpenAI(api_key=api_key)

    payload = text if len(text) <= OPENAI_TTS_INPUT_LIMIT else text[:OPENAI_TTS_INPUT_LIMIT]
    if len(payload) < len(text):
        logger.warning(
            "audio.tts.openai: input truncated %d → %d chars",
            len(text), len(payload),
        )

    logger.info(
        "audio.tts.openai: → model=%s voice=%s fmt=%s chars=%d",
        model, voice, audio_format, len(payload),
    )
    t0 = time.perf_counter()
    try:
        resp = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=payload,
            response_format=audio_format,
        )
    except Exception as exc:
        took_ms = (time.perf_counter() - t0) * 1000
        body = getattr(exc, "body", None) or getattr(exc, "response", None)
        logger.error(
            "audio.tts.openai: ← FAIL took=%dms class=%s msg=%s body=%s",
            int(took_ms), exc.__class__.__name__, str(exc), repr(body)[:500],
        )
        raise

    audio_bytes = await resp.aread() if hasattr(resp, "aread") else resp.read()
    took_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "audio.tts.openai: ← OK took=%dms bytes=%d voice=%s model=%s fmt=%s",
        int(took_ms), len(audio_bytes), voice, model, audio_format,
    )

    return Synthesis(
        audio=audio_bytes,
        mime=_mime_for_format(audio_format),
        model=model,
        provider="openai",
        voice=voice,
    )


def _mime_for_format(fmt: str) -> str:
    return {
        "mp3":  "audio/mpeg",
        "opus": "audio/ogg",
        "aac":  "audio/aac",
        "flac": "audio/flac",
        "wav":  "audio/wav",
    }.get(fmt.lower(), "application/octet-stream")
