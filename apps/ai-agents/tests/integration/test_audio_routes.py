"""Integration tests for the /internal/audio/* endpoints.

Both endpoints sit behind the X-Internal-Token guard and exercise the
DB + OpenAI in production. Tests bypass:
- ``require_internal_token``  → no header expected
- ``transcribe_bytes``        → fake Transcription
- ``InsightExtractionChain``  → fake extracted list
- ``MemoryService``           → fake stored insights

What we validate:
- /transcribe returns the provider's text + segments + model fields
- /transcribe rejects empty payloads (400)
- /extract_insights stores insights tagged with the caller's source string
- /extract_insights short-circuits to ``stored=0`` when no insights are found
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session, get_llm_provider
from app.api.internal_auth import require_internal_token
from app.audio.transcription import Transcription, TranscriptionSegment
from app.main import app

# ── Helpers ────────────────────────────────────────────────────────────


def _override_internal_auth() -> None:
    """No-op the X-Internal-Token guard for tests."""

    async def _ok() -> None:
        return None

    app.dependency_overrides[require_internal_token] = _ok


def _override_db_session(session: object) -> None:
    """Inject a fake DB session — endpoints don't actually use it once
    the MemoryService is replaced, but the dependency must still resolve."""

    async def _yield() -> AsyncIterator[object]:
        yield session

    app.dependency_overrides[get_db_session] = _yield


def _override_llm() -> None:
    app.dependency_overrides[get_llm_provider] = lambda: MagicMock()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _override_internal_auth()
    _override_db_session(MagicMock())
    _override_llm()

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ── /internal/audio/transcribe ─────────────────────────────────────────


@pytest.mark.asyncio
class TestTranscribeRoute:
    async def test_returns_text_and_segments(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = Transcription(
            text="hola mundo",
            language="es",
            segments=[TranscriptionSegment(0.0, 1.0, "hola mundo")],
            model="whisper-1",
            provider="openai",
        )

        async def _fake_transcribe(*_args: object, **_kwargs: object) -> Transcription:
            return fake

        monkeypatch.setattr(
            "app.api.routes.audio.transcribe_bytes", _fake_transcribe
        )

        files = {"audio": ("chunk.m4a", b"fake-audio-bytes", "audio/m4a")}
        data = {"user_id": "u-1", "language": "es"}
        resp = await client.post("/internal/audio/transcribe", files=files, data=data)

        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "hola mundo"
        assert body["language"] == "es"
        assert body["model"] == "whisper-1"
        assert body["provider"] == "openai"
        assert body["segments"] == [{"start": 0.0, "end": 1.0, "text": "hola mundo"}]

    async def test_empty_payload_400(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # transcribe_bytes should never be invoked for empty payloads
        called = {"hit": False}

        async def _fake_transcribe(*_args: object, **_kwargs: object) -> Transcription:
            called["hit"] = True
            return Transcription(text="", language=None)

        monkeypatch.setattr(
            "app.api.routes.audio.transcribe_bytes", _fake_transcribe
        )

        files = {"audio": ("chunk.m4a", b"", "audio/m4a")}
        data = {"user_id": "u-1"}
        resp = await client.post("/internal/audio/transcribe", files=files, data=data)

        assert resp.status_code == 400
        assert called["hit"] is False


# ── /internal/audio/extract_insights ───────────────────────────────────


@pytest.mark.asyncio
class TestExtractInsightsRoute:
    async def test_stores_with_source_tag(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_extracted = [
            SimpleNamespace(category="preference", content="le gusta el café", confidence=0.9),
        ]
        chain_instance = MagicMock()
        chain_instance.extract = AsyncMock(return_value=fake_extracted)
        monkeypatch.setattr(
            "app.api.routes.audio.InsightExtractionChain",
            lambda **_kw: chain_instance,
        )

        # avoid hitting OpenAI for embeddings
        monkeypatch.setattr(
            "app.api.routes.audio.get_embeddings", lambda *_a, **_k: MagicMock()
        )

        stored_insight = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            user_id="u-1",
            category="preference",
            content="le gusta el café",
            confidence=0.9,
            source="audio:s-42",
            created_at=datetime.now(UTC),
        )
        memory_instance = MagicMock()
        memory_instance.store_insights = AsyncMock(return_value=[stored_insight])
        captured_kwargs: dict = {}

        async def _store(**kwargs: object) -> list:
            captured_kwargs.update(kwargs)
            return [stored_insight]

        memory_instance.store_insights = _store
        monkeypatch.setattr(
            "app.api.routes.audio.MemoryService",
            lambda **_kw: memory_instance,
        )

        resp = await client.post(
            "/internal/audio/extract_insights",
            json={
                "user_id": "u-1",
                "transcript": "Hoy desayuné café con leche",
                "source": "audio:s-42",
                "context": "",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["stored"] == 1
        assert body["source"] == "audio:s-42"
        assert body["insights"][0]["source"] == "audio:s-42"
        # extract called with the transcript text
        chain_instance.extract.assert_awaited_once()
        kw = chain_instance.extract.await_args.kwargs
        assert kw["message"] == "Hoy desayuné café con leche"
        # store_insights forwarded the user's source label
        assert captured_kwargs["source"] == "audio:s-42"
        assert captured_kwargs["user_id"] == "u-1"

    async def test_no_insights_short_circuit(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chain_instance = MagicMock()
        chain_instance.extract = AsyncMock(return_value=[])
        monkeypatch.setattr(
            "app.api.routes.audio.InsightExtractionChain",
            lambda **_kw: chain_instance,
        )
        # MemoryService should never be constructed in the empty path; if it
        # is, the test will explode — that's the point.
        monkeypatch.setattr(
            "app.api.routes.audio.get_embeddings",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("get_embeddings called")),
        )

        resp = await client.post(
            "/internal/audio/extract_insights",
            json={
                "user_id": "u-1",
                "transcript": "uh, ok",
                "source": "audio:s-1",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"insights": [], "stored": 0}
