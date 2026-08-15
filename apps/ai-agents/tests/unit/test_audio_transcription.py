"""Unit tests for app.audio.transcription.

These tests stub the OpenAI client so we never make a real API call.
They cover:
- gpt-4o-mini-transcribe path (no segments, language carried through)
- whisper-1 path (segments parsed, ``response_format="verbose_json"`` set)
- error path when ``OPENAI_API_KEY`` is empty
- unknown provider raises ``ValueError``
- provider failures wrapped in ``TranscriptionError`` with a classified
  ``kind`` (quota / unsupported_format / provider_error) — DEV-97
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from app.audio.transcription import (
    Transcription,
    TranscriptionError,
    TranscriptionSegment,
    classify_provider_error,
    transcribe_bytes,
)
from app.config.settings import Settings


def _settings(*, model: str = "gpt-4o-mini-transcribe", api_key: str = "sk-test") -> Settings:
    return Settings(
        openai_api_key=SecretStr(api_key),
        audio_transcription_provider="openai",
        audio_transcription_model=model,
        internal_token="t",
    )


@pytest.mark.asyncio
class TestTranscribeBytes:
    async def test_gpt4o_mini_returns_text_only(self) -> None:
        settings = _settings(model="gpt-4o-mini-transcribe")
        fake_resp = SimpleNamespace(text="hola mundo", language="es")

        with patch("app.audio.transcription.AsyncOpenAI") as fake_client_cls:
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(return_value=fake_resp)
            fake_client_cls.return_value = client

            result = await transcribe_bytes(
                b"fake-audio-bytes",
                settings=settings,
                filename="chunk.m4a",
                mime="audio/m4a",
                language="es",
            )

        assert isinstance(result, Transcription)
        assert result.text == "hola mundo"
        assert result.language == "es"
        assert result.segments == []
        assert result.model == "gpt-4o-mini-transcribe"
        assert result.provider == "openai"

        kwargs = client.audio.transcriptions.create.await_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini-transcribe"
        assert kwargs["language"] == "es"
        assert "response_format" not in kwargs

    async def test_whisper1_parses_segments(self) -> None:
        settings = _settings(model="whisper-1")
        seg1 = SimpleNamespace(start=0.0, end=1.5, text="hola")
        seg2 = SimpleNamespace(start=1.5, end=3.0, text="mundo")
        fake_resp = SimpleNamespace(
            text="hola mundo", language="es", segments=[seg1, seg2]
        )

        with patch("app.audio.transcription.AsyncOpenAI") as fake_client_cls:
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(return_value=fake_resp)
            fake_client_cls.return_value = client

            result = await transcribe_bytes(
                b"x", settings=settings, language=None
            )

        assert result.segments == [
            TranscriptionSegment(start=0.0, end=1.5, text="hola"),
            TranscriptionSegment(start=1.5, end=3.0, text="mundo"),
        ]
        kwargs = client.audio.transcriptions.create.await_args.kwargs
        assert kwargs["response_format"] == "verbose_json"
        assert "language" not in kwargs

    async def test_missing_api_key_raises(self) -> None:
        settings = _settings(api_key="")
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            await transcribe_bytes(b"x", settings=settings)

    async def test_missing_api_key_is_provider_error_kind(self) -> None:
        settings = _settings(api_key="")
        with pytest.raises(TranscriptionError) as exc_info:
            await transcribe_bytes(b"x", settings=settings)
        assert exc_info.value.kind == "provider_error"

    async def test_provider_429_raises_quota_kind(self) -> None:
        settings = _settings()
        boom = Exception("Rate limit reached / insufficient_quota")
        boom.status_code = 429  # type: ignore[attr-defined]

        with patch("app.audio.transcription.AsyncOpenAI") as fake_client_cls:
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(side_effect=boom)
            fake_client_cls.return_value = client

            with pytest.raises(TranscriptionError) as exc_info:
                await transcribe_bytes(b"x", settings=settings)

        assert exc_info.value.kind == "quota"
        assert exc_info.value.__cause__ is boom

    async def test_provider_400_raises_unsupported_format_kind(self) -> None:
        settings = _settings()
        boom = Exception("Invalid file format.")
        boom.status_code = 400  # type: ignore[attr-defined]

        with patch("app.audio.transcription.AsyncOpenAI") as fake_client_cls:
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(side_effect=boom)
            fake_client_cls.return_value = client

            with pytest.raises(TranscriptionError) as exc_info:
                await transcribe_bytes(b"x", settings=settings)

        assert exc_info.value.kind == "unsupported_format"

    async def test_provider_5xx_raises_provider_error_kind(self) -> None:
        settings = _settings()
        boom = Exception("upstream exploded")
        boom.status_code = 500  # type: ignore[attr-defined]

        with patch("app.audio.transcription.AsyncOpenAI") as fake_client_cls:
            client = MagicMock()
            client.audio.transcriptions.create = AsyncMock(side_effect=boom)
            fake_client_cls.return_value = client

            with pytest.raises(TranscriptionError) as exc_info:
                await transcribe_bytes(b"x", settings=settings)

        assert exc_info.value.kind == "provider_error"

    async def test_unknown_provider_raises(self) -> None:
        settings = Settings(
            openai_api_key=SecretStr("sk-test"),
            audio_transcription_provider="self_hosted",
            audio_transcription_model="whisper-1",
            internal_token="t",
        )
        with pytest.raises(ValueError, match="Unknown AUDIO_TRANSCRIPTION_PROVIDER"):
            await transcribe_bytes(b"x", settings=settings)

    async def test_auth_error_is_provider_error_not_unsupported(self) -> None:
        # 401/403 are excluded from the 4xx → unsupported_format bucket.
        boom = Exception("Incorrect API key provided")
        boom.status_code = 401  # type: ignore[attr-defined]
        assert classify_provider_error(boom) == "provider_error"

    async def test_classify_without_status_falls_back_to_message(self) -> None:
        assert classify_provider_error(Exception("insufficient_quota for org")) == "quota"
        assert classify_provider_error(Exception("Unsupported codec")) == "unsupported_format"
        assert classify_provider_error(Exception("connection reset")) == "provider_error"

    async def test_to_dict_serializes_segments(self) -> None:
        t = Transcription(
            text="hi",
            language="en",
            segments=[TranscriptionSegment(0.0, 1.0, "hi")],
            model="whisper-1",
            provider="openai",
        )
        assert t.to_dict() == {
            "text": "hi",
            "language": "en",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "model": "whisper-1",
            "provider": "openai",
        }
