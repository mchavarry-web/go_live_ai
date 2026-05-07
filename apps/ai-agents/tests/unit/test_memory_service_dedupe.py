"""Unit tests for ``MemoryService.store_insights`` pre-insert dedupe.

Wave A.3 (2026-05-06). The tests stub the embeddings + repository so we
can exercise the three dedupe branches without a live DB or LLM:

  - no near-duplicate → fresh insert
  - near-duplicate, lower confidence → reuse existing row, no insert
  - near-duplicate, higher confidence → update existing row in place
  - dedupe=False → bypass the lookup entirely
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory_service import MemoryService


def _row(*, id_: str, confidence: float, content: str = "old"):
    return SimpleNamespace(
        id=id_, content=content, confidence=confidence, source="conversation"
    )


def _build_service(*, near_duplicate=None, embed_dim: int = 4):
    """Return a service with stubbed embeddings + repository.

    ``near_duplicate`` — when set, the search_similar mock returns this
    row, simulating an existing same-user/same-category insight.
    """
    embeddings = MagicMock()
    embeddings.aembed_documents = AsyncMock(
        return_value=[[0.1] * embed_dim, [0.2] * embed_dim]
    )
    embeddings.aembed_query = AsyncMock(return_value=[0.3] * embed_dim)

    repo = MagicMock()
    repo.search_similar = AsyncMock(
        return_value=[near_duplicate] if near_duplicate is not None else []
    )
    repo.create_with_embedding = AsyncMock(
        side_effect=lambda **kw: _row(id_="new", confidence=kw["confidence"], content=kw["content"])
    )
    repo.update_content = AsyncMock(
        side_effect=lambda **kw: _row(
            id_=kw["insight_id"], confidence=0.0, content=kw["content"]
        )
    )

    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    svc = MemoryService.__new__(MemoryService)
    svc._session = session
    svc.repository = repo
    svc.embeddings = embeddings
    return svc


@pytest.mark.asyncio
async def test_no_near_duplicate_creates_new_row() -> None:
    svc = _build_service(near_duplicate=None)
    out = await svc.store_insights(
        user_id="u1",
        insights=[
            {"category": "preference", "content": "le gusta el café", "confidence": 0.7},
        ],
    )
    assert len(out) == 1
    assert out[0].id == "new"
    svc.repository.create_with_embedding.assert_called_once()
    svc.repository.update_content.assert_not_called()


@pytest.mark.asyncio
async def test_near_duplicate_lower_confidence_skips_insert() -> None:
    existing = _row(id_="exists", confidence=0.9, content="le gusta el café")
    svc = _build_service(near_duplicate=existing)

    out = await svc.store_insights(
        user_id="u1",
        insights=[
            {"category": "preference", "content": "le gusta el café", "confidence": 0.7},
        ],
    )
    assert len(out) == 1
    assert out[0].id == "exists"
    svc.repository.create_with_embedding.assert_not_called()
    svc.repository.update_content.assert_not_called()


@pytest.mark.asyncio
async def test_near_duplicate_higher_confidence_updates_in_place() -> None:
    existing = _row(id_="exists", confidence=0.5, content="le gusta el café")
    svc = _build_service(near_duplicate=existing)

    out = await svc.store_insights(
        user_id="u1",
        insights=[
            {
                "category": "preference",
                "content": "le encanta el café con leche",
                "confidence": 0.9,  # +0.40 over existing — well above 0.10 uplift
            },
        ],
    )
    assert len(out) == 1
    assert out[0].id == "exists"
    svc.repository.update_content.assert_called_once()
    svc.repository.create_with_embedding.assert_not_called()


@pytest.mark.asyncio
async def test_dedupe_false_skips_lookup() -> None:
    existing = _row(id_="exists", confidence=0.9, content="X")
    svc = _build_service(near_duplicate=existing)

    out = await svc.store_insights(
        user_id="u1",
        insights=[{"category": "preference", "content": "X", "confidence": 0.7}],
        dedupe=False,
    )
    assert len(out) == 1
    assert out[0].id == "new"
    svc.repository.search_similar.assert_not_called()
    svc.repository.create_with_embedding.assert_called_once()


@pytest.mark.asyncio
async def test_batch_embeddings_used_for_multiple_inserts() -> None:
    svc = _build_service(near_duplicate=None)
    await svc.store_insights(
        user_id="u1",
        insights=[
            {"category": "preference", "content": "A", "confidence": 0.7},
            {"category": "preference", "content": "B", "confidence": 0.7},
        ],
    )
    # The cheaper batched call should win over per-insight aembed_query.
    svc.embeddings.aembed_documents.assert_awaited_once()
    svc.embeddings.aembed_query.assert_not_called()
