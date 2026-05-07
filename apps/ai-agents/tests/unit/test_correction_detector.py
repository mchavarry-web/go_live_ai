"""Wave B.1 — correction detector chain + supersede service path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.language_models import BaseChatModel

from app.chains.correction_detector_chain import (
    CorrectionDetectorChain,
    CorrectionSignal,
    CorrectionSignals,
)
from app.services.memory_service import MemoryService


# ── Chain ───────────────────────────────────────────────────────────────


def _build_chain(canned: list[CorrectionSignal]) -> CorrectionDetectorChain:
    chain = CorrectionDetectorChain(llm=MagicMock(spec=BaseChatModel))
    chain.chain = MagicMock()
    chain.chain.ainvoke = AsyncMock(
        return_value=CorrectionSignals(corrections=canned)
    )
    return chain


@pytest.mark.asyncio
async def test_empty_message_returns_empty() -> None:
    chain = _build_chain(canned=[])
    assert await chain.detect("") == []
    assert await chain.detect("   ") == []


@pytest.mark.asyncio
async def test_low_confidence_signals_dropped() -> None:
    chain = _build_chain(
        canned=[
            CorrectionSignal(target_phrase="le gusta el café", confidence=0.5),
            CorrectionSignal(target_phrase="le gusta el café", confidence=0.85),
        ]
    )
    out = await chain.detect("ya no me gusta el café")
    assert len(out) == 1
    assert out[0].confidence == 0.85


@pytest.mark.asyncio
async def test_chain_failure_yields_empty() -> None:
    chain = CorrectionDetectorChain(llm=MagicMock(spec=BaseChatModel))
    chain.chain = MagicMock()
    chain.chain.ainvoke = AsyncMock(side_effect=RuntimeError("LLM exploded"))
    out = await chain.detect("anything")
    assert out == []


# ── Service ─────────────────────────────────────────────────────────────


def _stub_memory_service(matches=None) -> MemoryService:
    embeddings = MagicMock()
    embeddings.aembed_query = AsyncMock(return_value=[0.0] * 4)
    repo = MagicMock()
    repo.search_similar = AsyncMock(return_value=matches or [])
    repo.supersede_ids = AsyncMock(return_value=len(matches or []))

    svc = MemoryService.__new__(MemoryService)
    svc._session = MagicMock()
    svc.repository = repo
    svc.embeddings = embeddings
    return svc


@pytest.mark.asyncio
async def test_apply_corrections_supersedes_matches() -> None:
    matches = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    svc = _stub_memory_service(matches=matches)
    sig = CorrectionSignal(target_phrase="le gusta el café", confidence=0.9)

    count = await svc.apply_corrections("u1", [sig])
    assert count == 2
    svc.repository.supersede_ids.assert_awaited_once_with(
        user_id="u1",
        insight_ids=["a", "b"],
        status="superseded",
    )


@pytest.mark.asyncio
async def test_apply_corrections_no_match_no_call() -> None:
    svc = _stub_memory_service(matches=[])
    sig = CorrectionSignal(target_phrase="le gusta el té", confidence=0.9)
    count = await svc.apply_corrections("u1", [sig])
    assert count == 0
    svc.repository.supersede_ids.assert_not_called()


@pytest.mark.asyncio
async def test_apply_corrections_uses_category_hint() -> None:
    svc = _stub_memory_service(matches=[SimpleNamespace(id="a")])
    sig = CorrectionSignal(
        target_phrase="trabaja en X",
        confidence=0.9,
        category_hint="personal_history",
    )
    await svc.apply_corrections("u1", [sig])
    call_kwargs = svc.repository.search_similar.await_args.kwargs
    assert call_kwargs["categories"] == ["personal_history"]
