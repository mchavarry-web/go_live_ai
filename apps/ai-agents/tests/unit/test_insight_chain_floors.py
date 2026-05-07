"""Wave B.2 — per-category confidence floors.

The chain's LLM call is mocked; we exercise only the post-extraction
filter to verify the right per-category cutoffs.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.language_models import BaseChatModel

from app.chains.insight_chain import (
    ExtractedInsight,
    ExtractedInsights,
    InsightExtractionChain,
)


def _build_chain_with_canned(insights: list[ExtractedInsight]) -> InsightExtractionChain:
    chain = InsightExtractionChain(llm=MagicMock(spec=BaseChatModel))
    chain.chain = MagicMock()
    chain.chain.ainvoke = AsyncMock(return_value=ExtractedInsights(insights=insights))
    return chain


@pytest.mark.asyncio
async def test_default_base_floor_is_055() -> None:
    chain = InsightExtractionChain(llm=MagicMock(spec=BaseChatModel))
    assert chain.min_confidence == 0.55


@pytest.mark.asyncio
async def test_sensitive_categories_have_higher_floor() -> None:
    chain = InsightExtractionChain(llm=MagicMock(spec=BaseChatModel))
    assert chain.category_min_confidence["health"] == 0.65
    assert chain.category_min_confidence["relationship"] == 0.65
    assert chain.category_min_confidence["emotion"] == 0.65


@pytest.mark.asyncio
async def test_preference_passes_at_055_but_health_drops() -> None:
    chain = _build_chain_with_canned(
        [
            ExtractedInsight(category="preference", content="le gusta el café", confidence=0.55),
            # Health at 0.55 must be rejected (sensitive floor 0.65).
            ExtractedInsight(category="health", content="duerme mal", confidence=0.55),
            # Health at 0.70 passes.
            ExtractedInsight(category="health", content="hace pesas", confidence=0.70),
        ]
    )
    out = await chain.extract(message="dummy")
    categories = [i.category for i in out]
    assert "preference" in categories
    assert categories.count("health") == 1, [(i.category, i.confidence) for i in out]


@pytest.mark.asyncio
async def test_explicit_overrides_take_precedence() -> None:
    """Callers can pass a stricter floor (e.g. for action-usable retrieval)."""
    chain = InsightExtractionChain(
        llm=MagicMock(spec=BaseChatModel),
        min_confidence=0.80,
        category_min_confidence={},  # no per-category exceptions
    )
    chain.chain = MagicMock()
    chain.chain.ainvoke = AsyncMock(
        return_value=ExtractedInsights(
            insights=[
                ExtractedInsight(category="preference", content="X", confidence=0.79),
                ExtractedInsight(category="preference", content="Y", confidence=0.81),
            ]
        )
    )
    out = await chain.extract(message="dummy")
    assert [i.content for i in out] == ["Y"]


@pytest.mark.asyncio
async def test_legacy_caller_can_opt_into_loose_floor() -> None:
    """Tests / debug paths can still set a loose floor explicitly."""
    chain = InsightExtractionChain(
        llm=MagicMock(spec=BaseChatModel),
        min_confidence=0.4,
        category_min_confidence={},
    )
    chain.chain = MagicMock()
    chain.chain.ainvoke = AsyncMock(
        return_value=ExtractedInsights(
            insights=[
                ExtractedInsight(category="health", content="X", confidence=0.45),
            ]
        )
    )
    out = await chain.extract(message="dummy")
    assert len(out) == 1
