"""Integration tests for DELETE /internal/memory/{user_id}/by-source.

Drives the route through the FastAPI ASGI transport. Bypasses the
internal-token guard, fakes the DB session, and replaces ``MemoryService``
so we can assert the parameters the route forwards.
"""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db_session
from app.api.internal_auth import require_internal_token
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async def _ok() -> None:
        return None

    async def _yield() -> AsyncIterator[object]:
        yield MagicMock()

    app.dependency_overrides[require_internal_token] = _ok
    app.dependency_overrides[get_db_session] = _yield

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestDeleteBySourceRoute:
    async def test_exact_match(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        async def _delete(*, user_id: str, source: str, prefix: bool) -> int:
            captured.update({"user_id": user_id, "source": source, "prefix": prefix})
            return 3

        memory_instance = MagicMock()
        memory_instance.delete_insights_by_source = _delete
        monkeypatch.setattr(
            "app.api.routes.memory.MemoryService",
            lambda **_kw: memory_instance,
        )
        monkeypatch.setattr(
            "app.api.routes.memory.get_embeddings", lambda *_a, **_k: MagicMock()
        )

        resp = await client.delete(
            "/internal/memory/u-1/by-source",
            params={"source": "audio:s-1"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 3, "source": "audio:s-1", "prefix": False}
        assert captured == {"user_id": "u-1", "source": "audio:s-1", "prefix": False}

    async def test_prefix_match(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        async def _delete(*, user_id: str, source: str, prefix: bool) -> int:
            captured.update({"user_id": user_id, "source": source, "prefix": prefix})
            return 17

        memory_instance = MagicMock()
        memory_instance.delete_insights_by_source = _delete
        monkeypatch.setattr(
            "app.api.routes.memory.MemoryService",
            lambda **_kw: memory_instance,
        )
        monkeypatch.setattr(
            "app.api.routes.memory.get_embeddings", lambda *_a, **_k: MagicMock()
        )

        resp = await client.delete(
            "/internal/memory/u-1/by-source",
            params={"source": "audio", "prefix": "true"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 17, "source": "audio", "prefix": True}
        assert captured["prefix"] is True
        assert captured["source"] == "audio"
