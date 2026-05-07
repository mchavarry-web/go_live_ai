"""Wave B.4 — durable ``ChatService.learn`` entrypoint.

Drives the public method with stubbed sub-tasks so we can verify the
counts come back in the right shape without standing up a real DB or LLM.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.schemas import LearnRequest, LearnResponse


@pytest.mark.asyncio
async def test_learn_request_schema_round_trip() -> None:
    payload = LearnRequest(
        user_id="u1",
        conversation_id="c1",
        user_message="hola",
        assistant_response="¡hola!",
        conversation_history=[
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "¡hola!"},
        ],
        active_mode="friends",
        turn_count=2,
        timezone="America/Lima",
    )
    assert payload.user_id == "u1"
    assert payload.active_mode == "friends"
    assert payload.turn_count == 2
    # mode should be enum-validated
    with pytest.raises(Exception):
        LearnRequest(
            user_id="u",
            conversation_id="c",
            user_message="hi",
            active_mode="not_a_real_mode",  # type: ignore[arg-type]
        )


def test_learn_response_defaults_zero() -> None:
    r = LearnResponse()
    assert r.insights_new == 0
    assert r.events_new == 0
    assert r.summary_written is False
    assert r.took_ms == 0


@pytest.mark.asyncio
async def test_learn_drives_underlying_chains() -> None:
    """ChatService.learn must call insight + persona + event extraction
    and return aggregated counts. We stub each branch."""
    from app.services.chat_service import ChatService

    svc = ChatService.__new__(ChatService)
    svc.llm = MagicMock()
    svc.embeddings = MagicMock()
    svc.settings = MagicMock()
    svc.settings.post_turn_inline = False
    # Stub the helper methods invoked by learn().
    svc._get_memory_insights = AsyncMock(return_value=[])
    svc._get_persona_insights = AsyncMock(return_value=[])
    svc._detect_and_apply_corrections = AsyncMock(return_value=2)
    svc._extract_and_store_insights = AsyncMock(
        return_value=[MagicMock(), MagicMock(), MagicMock()]
    )
    svc._evolve_and_store_persona = AsyncMock(return_value=[MagicMock()])
    svc._extract_and_store_events = AsyncMock(return_value=[MagicMock()])
    svc._calibrate_and_store_slang = AsyncMock(return_value=None)

    session = MagicMock()
    counts = await svc.learn(
        session=session,
        user_id="u1",
        conversation_id="c1",
        user_message="hola",
        assistant_response="¡hola!",
        conversation_history=[
            {"role": "user", "content": "hola"},
        ],
        active_mode="friends",
        turn_count=1,
    )
    assert counts["insights_superseded"] == 2
    assert counts["insights_new"] == 3
    assert counts["events_new"] == 1
    assert counts["persona_notes"] == 1
    assert counts["took_ms"] >= 0
    svc._extract_and_store_insights.assert_awaited_once()
    svc._evolve_and_store_persona.assert_awaited_once()
    svc._extract_and_store_events.assert_awaited_once()
