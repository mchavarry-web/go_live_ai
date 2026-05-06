"""Unit tests for the event extraction chain.

Mocks the LCEL chain so we can exercise the resolution logic without an
LLM. Verifies the LLM/dateparser cross-check and the windowing/confidence
filters.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel

from app.chains.event_extraction_chain import (
    EventExtractionChain,
    ExtractedEvent,
    ExtractedEvents,
)


# Reference "now": Tuesday 2026-05-05 17:00 UTC = 12:00 Lima (UTC-5).
_NOW_UTC = datetime(2026, 5, 5, 17, 0, tzinfo=UTC)
_MSG_AT = _NOW_UTC
_LIMA = "America/Lima"


def _build_chain_with_canned(events: list[ExtractedEvent]) -> EventExtractionChain:
    """Build a chain whose LCEL pipeline returns the supplied events."""
    chain = EventExtractionChain(llm=MagicMock(spec=BaseChatModel))

    async def _fake_ainvoke(_inputs: dict) -> ExtractedEvents:
        return ExtractedEvents(events=events)

    chain.chain = MagicMock()
    chain.chain.ainvoke = _fake_ainvoke  # type: ignore[assignment]
    return chain


class TestParsers:
    """Static parsers for ISO and dateparser inputs."""

    def test_iso_with_offset_normalizes_to_utc(self) -> None:
        out = EventExtractionChain._parse_llm_iso(
            "2026-05-12T15:00:00-05:00", user_tz=_LIMA
        )
        assert out == datetime(2026, 5, 12, 20, 0, tzinfo=UTC)

    def test_naive_iso_attaches_user_tz(self) -> None:
        out = EventExtractionChain._parse_llm_iso(
            "2026-05-12T15:00:00", user_tz=_LIMA
        )
        assert out == datetime(2026, 5, 12, 20, 0, tzinfo=UTC)

    def test_garbage_iso_returns_none(self) -> None:
        assert (
            EventExtractionChain._parse_llm_iso("not-a-date", user_tz=_LIMA) is None
        )

    def test_invalid_tz_returns_none(self) -> None:
        # Naive ISO + invalid tz cannot be normalised.
        assert (
            EventExtractionChain._parse_llm_iso(
                "2026-05-12T15:00:00", user_tz="Not/A_Zone"
            )
            is None
        )

    def test_dateparser_handles_relative_phrase(self) -> None:
        out = EventExtractionChain._parse_with_dateparser(
            raw_text="mañana a las 3pm",
            user_tz=_LIMA,
            relative_base=_MSG_AT,
        )
        assert out is not None
        # Tomorrow at 3pm Lima = 20:00 UTC the day after _MSG_AT in Lima
        assert out.tzinfo is UTC
        assert out.date() == datetime(2026, 5, 6).date()


class TestWindowAndConfidenceFilters:
    """``_within_window`` clamps acceptance to [now-1h, now+horizon]."""

    def test_recent_past_is_rejected_beyond_one_hour(self) -> None:
        chain = EventExtractionChain(llm=MagicMock(spec=BaseChatModel))
        too_old = datetime(2026, 5, 5, 14, 0, tzinfo=UTC)  # 3h before now
        assert chain._within_window(too_old, now_utc=_NOW_UTC) is False

    def test_within_one_hour_past_accepted(self) -> None:
        chain = EventExtractionChain(llm=MagicMock(spec=BaseChatModel))
        slightly_past = datetime(2026, 5, 5, 16, 30, tzinfo=UTC)  # 30 min before
        assert chain._within_window(slightly_past, now_utc=_NOW_UTC) is True

    def test_far_future_rejected(self) -> None:
        chain = EventExtractionChain(
            llm=MagicMock(spec=BaseChatModel), future_horizon_days=30
        )
        too_far = datetime(2026, 8, 1, tzinfo=UTC)
        assert chain._within_window(too_far, now_utc=_NOW_UTC) is False


class TestExtractEndToEnd:
    """``extract`` filters confidence, resolves timestamps, and dedupes drops."""

    @pytest.mark.asyncio
    async def test_low_confidence_dropped(self) -> None:
        chain = _build_chain_with_canned(
            [
                ExtractedEvent(
                    title="dentista",
                    occurs_at_iso="2026-05-06T15:00:00-05:00",
                    has_explicit_time=True,
                    raw_text="mañana a las 3",
                    confidence=0.3,  # below 0.6 floor
                )
            ]
        )
        out = await chain.extract(
            message="mañana a las 3",
            now_utc=_NOW_UTC,
            timezone=_LIMA,
            message_created_at=_MSG_AT,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_clear_event_resolves_to_utc(self) -> None:
        chain = _build_chain_with_canned(
            [
                ExtractedEvent(
                    title="dentista",
                    occurs_at_iso="2026-05-06T15:00:00-05:00",
                    has_explicit_time=True,
                    raw_text="mañana a las 3pm",
                    confidence=0.9,
                )
            ]
        )
        out = await chain.extract(
            message="tengo dentista mañana a las 3pm",
            now_utc=_NOW_UTC,
            timezone=_LIMA,
            message_created_at=_MSG_AT,
        )
        assert len(out) == 1
        ev = out[0]
        assert ev.title == "dentista"
        assert ev.occurs_at == datetime(2026, 5, 6, 20, 0, tzinfo=UTC)
        assert ev.occurs_at_has_time is True

    @pytest.mark.asyncio
    async def test_hallucinated_far_past_dropped(self) -> None:
        # LLM returns an absurdly old date — fails _within_window.
        chain = _build_chain_with_canned(
            [
                ExtractedEvent(
                    title="reunión",
                    occurs_at_iso="2020-01-01T10:00:00-05:00",
                    has_explicit_time=True,
                    raw_text="reunión el lunes",
                    confidence=0.9,
                )
            ]
        )
        out = await chain.extract(
            message="reunión el lunes",
            now_utc=_NOW_UTC,
            timezone=_LIMA,
            message_created_at=_MSG_AT,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_empty_title_dropped(self) -> None:
        chain = _build_chain_with_canned(
            [
                ExtractedEvent(
                    title="   ",
                    occurs_at_iso="2026-05-06T10:00:00-05:00",
                    has_explicit_time=True,
                    raw_text="mañana",
                    confidence=0.9,
                )
            ]
        )
        out = await chain.extract(
            message="mañana",
            now_utc=_NOW_UTC,
            timezone=_LIMA,
            message_created_at=_MSG_AT,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_chain_failure_returns_empty(self) -> None:
        chain = EventExtractionChain(llm=MagicMock(spec=BaseChatModel))

        async def _boom(_inputs: dict) -> ExtractedEvents:
            raise RuntimeError("LLM exploded")

        chain.chain = MagicMock()
        chain.chain.ainvoke = _boom  # type: ignore[assignment]

        out = await chain.extract(
            message="anything",
            now_utc=_NOW_UTC,
            timezone=_LIMA,
            message_created_at=_MSG_AT,
        )
        assert out == []
