"""Unit tests for the autonomous agent features.

Covers:
- InsightCategory.AVATAR_EVOLUTION enum value
- ChatService._extract_user_profile with persona_insights
- InsightExtractionChain.extract with assistant_response parameter
- PersonaEvolutionChain (mocked LLM)
- build_avatar_system_prompt with persona_insights
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from app.chains.insight_chain import (
    ExtractedInsight,
    ExtractedInsights,
    InsightExtractionChain,
)
from app.chains.persona_evolution_chain import PersonaEvolutionChain, PersonaNote, PersonaNotes
from app.models.enums import InsightCategory
from app.models.schemas import ChatGenerateRequest, UserProfile
from app.prompts.avatar_prompts import build_avatar_system_prompt, _build_persona_section
from app.services.chat_service import ChatService


# ── InsightCategory ──────────────────────────────────────────────────────


class TestInsightCategoryEnum:
    """Tests for the extended InsightCategory enum."""

    def test_avatar_evolution_value(self) -> None:
        assert InsightCategory.AVATAR_EVOLUTION.value == "avatar_evolution"

    def test_avatar_evolution_is_string(self) -> None:
        assert isinstance(InsightCategory.AVATAR_EVOLUTION, str)

    def test_all_expected_categories_exist(self) -> None:
        expected = {
            "personal_history", "preference", "relationship",
            "goal", "emotion", "health", "avatar_evolution",
            "language_style",
        }
        actual = {cat.value for cat in InsightCategory}
        assert expected.issubset(actual)

    def test_user_fact_categories_exclude_internal(self) -> None:
        _excluded = {InsightCategory.AVATAR_EVOLUTION, InsightCategory.LANGUAGE_STYLE}
        user_categories = [
            cat.value for cat in InsightCategory if cat not in _excluded
        ]
        assert InsightCategory.AVATAR_EVOLUTION.value not in user_categories
        assert InsightCategory.LANGUAGE_STYLE.value not in user_categories
        assert len(user_categories) == len(list(InsightCategory)) - len(_excluded)


# ── _build_persona_section ───────────────────────────────────────────────


class TestBuildPersonaSection:
    """Tests for the avatar persona section builder."""

    def test_empty_when_no_notes(self) -> None:
        assert _build_persona_section(None) == ""
        assert _build_persona_section([]) == ""

    def test_header_and_bullets(self) -> None:
        notes = ["Usa humor seco con frecuencia", "Evita temas de política"]
        result = _build_persona_section(notes)
        assert "TU VOZ Y EVOLUCIÓN CON ESTA PERSONA:" in result
        assert "- Usa humor seco con frecuencia" in result
        assert "- Evita temas de política" in result


# ── build_avatar_system_prompt with persona_insights ─────────────────────


class TestBuildAvatarSystemPromptPersona:
    """Tests that persona_insights are injected into the system prompt."""

    def _base_kwargs(self) -> dict:
        return {
            "avatar_name": "Juanito",
            "display_name": "Juan",
            "knowledge_level": 2,
            "current_datetime": "martes 31 de marzo de 2026, 10:00 hs",
        }

    def test_persona_section_injected(self) -> None:
        prompt = build_avatar_system_prompt(
            **self._base_kwargs(),
            persona_insights=["Suele usar lenguaje coloquial con Juan"],
        )
        assert "TU VOZ Y EVOLUCIÓN CON ESTA PERSONA:" in prompt
        assert "Suele usar lenguaje coloquial con Juan" in prompt

    def test_no_persona_section_when_none(self) -> None:
        prompt = build_avatar_system_prompt(
            **self._base_kwargs(),
            persona_insights=None,
        )
        assert "TU VOZ Y EVOLUCIÓN CON ESTA PERSONA:" not in prompt

    def test_persona_section_separate_from_insights(self) -> None:
        prompt = build_avatar_system_prompt(
            **self._base_kwargs(),
            insights=["Le gusta el fútbol"],
            persona_insights=["Tono directo y sin rodeos"],
        )
        assert "Le gusta el fútbol" in prompt
        assert "Tono directo y sin rodeos" in prompt
        # The persona header should appear separately
        assert "TU VOZ Y EVOLUCIÓN CON ESTA PERSONA:" in prompt
        assert "COSAS QUE SABES DE Juan:" in prompt


# ── ChatService._extract_user_profile ────────────────────────────────────


class TestChatServiceExtractUserProfile:
    """Tests for ChatService._extract_user_profile with persona_insights."""

    def _make_service(self, mock_llm: MagicMock) -> ChatService:
        from app.config.settings import Settings

        settings = Settings(
            openai_api_key="sk-test",  # type: ignore[arg-type]
            langchain_tracing_v2=False,
        )
        return ChatService(llm=mock_llm, settings=settings)

    def _make_request(self) -> ChatGenerateRequest:
        return ChatGenerateRequest(
            user_id="u1",
            message="Hola",
            conversation_id="c1",
            user_profile=UserProfile(
                display_name="Ana",
                avatar_name="Anita",
            ),
        )

    def test_persona_insights_included_in_profile(self, mock_llm: MagicMock) -> None:
        service = self._make_service(mock_llm)
        notes = ["Usa tono cálido con Ana"]
        profile = service._extract_user_profile(
            self._make_request(), persona_insights=notes
        )
        assert profile["persona_insights"] == notes

    def test_persona_insights_none_by_default(self, mock_llm: MagicMock) -> None:
        service = self._make_service(mock_llm)
        profile = service._extract_user_profile(self._make_request())
        assert profile["persona_insights"] is None

    def test_user_insights_and_persona_are_separate_keys(self, mock_llm: MagicMock) -> None:
        service = self._make_service(mock_llm)
        profile = service._extract_user_profile(
            self._make_request(),
            insights=["Le gusta el mate"],
            persona_insights=["Dialoga de forma informal"],
        )
        assert profile["insights"] == ["Le gusta el mate"]
        assert profile["persona_insights"] == ["Dialoga de forma informal"]

    def test_country_and_language_style_included(self, mock_llm: MagicMock) -> None:
        service = self._make_service(mock_llm)
        request = ChatGenerateRequest(
            user_id="u1",
            message="ya pe causa",
            conversation_id="c1",
            user_profile=UserProfile(
                display_name="Carlos",
                avatar_name="Carlitos",
                country="pe",
                introvert_extrovert=0.7,
                rational_emotional=0.3,
                values=["honestidad", "familia"],
            ),
        )
        profile = service._extract_user_profile(
            request,
            formality_level=0.3,
            custom_expressions=["ya pe"],
        )
        assert profile["country"] == "pe"
        assert profile["introvert_extrovert"] == 0.7
        assert profile["rational_emotional"] == 0.3
        assert profile["values"] == ["honestidad", "familia"]
        assert profile["formality_level"] == 0.3
        assert profile["custom_expressions"] == ["ya pe"]


# ── InsightExtractionChain with assistant_response ───────────────────────


class TestInsightExtractionChainWithTurn:
    """Tests for InsightExtractionChain.extract with a full conversation turn."""

    @pytest.mark.asyncio
    async def test_extract_passes_assistant_turn_to_chain(self, mock_llm: MagicMock) -> None:
        """The assistant_response should be formatted and passed as assistant_turn."""
        chain = InsightExtractionChain(llm=mock_llm)
        empty_result = ExtractedInsights(insights=[])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=empty_result)
            await chain.extract(
                message="Me duele la rodilla",
                assistant_response="Eso no suena bien, ¿desde cuándo?",
            )
            call_args = mock_chain.ainvoke.call_args[0][0]
            assert "Asistente: Eso no suena bien" in call_args["assistant_turn"]
            assert "Me duele la rodilla" in call_args["message"]

    @pytest.mark.asyncio
    async def test_extract_empty_assistant_turn_when_none(self, mock_llm: MagicMock) -> None:
        chain = InsightExtractionChain(llm=mock_llm)
        empty_result = ExtractedInsights(insights=[])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=empty_result)
            await chain.extract(message="Hola", assistant_response=None)
            call_args = mock_chain.ainvoke.call_args[0][0]
            assert call_args["assistant_turn"] == ""

    @pytest.mark.asyncio
    async def test_extract_filters_by_confidence(self, mock_llm: MagicMock) -> None:
        chain = InsightExtractionChain(llm=mock_llm, min_confidence=0.5)
        low = ExtractedInsight(category="preference", content="Le gusta el cine", confidence=0.3)
        high = ExtractedInsight(category="preference", content="Le gusta el fútbol", confidence=0.8)
        result = ExtractedInsights(insights=[low, high])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=result)
            insights = await chain.extract(message="Me gusta el fútbol")

        assert len(insights) == 1
        assert insights[0].content == "Le gusta el fútbol"

    @pytest.mark.asyncio
    async def test_extract_filters_invalid_categories(self, mock_llm: MagicMock) -> None:
        chain = InsightExtractionChain(llm=mock_llm)
        bad = ExtractedInsight(category="avatar_evolution", content="Algo", confidence=0.9)
        result = ExtractedInsights(insights=[bad])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=result)
            insights = await chain.extract(message="...")

        # avatar_evolution is NOT a valid user insight category
        assert insights == []


# ── PersonaEvolutionChain ────────────────────────────────────────────────


class TestPersonaEvolutionChain:
    """Tests for PersonaEvolutionChain.evolve."""

    @pytest.mark.asyncio
    async def test_evolve_returns_filtered_notes(self, mock_llm: MagicMock) -> None:
        chain = PersonaEvolutionChain(llm=mock_llm, min_confidence=0.5)
        low = PersonaNote(note="Patrón débil", confidence=0.3)
        high = PersonaNote(note="Usa humor constante", confidence=0.7)
        result = PersonaNotes(notes=[low, high])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=result)
            notes = await chain.evolve(
                user_message="Contame un chiste",
                assistant_response="¿Por qué el libro de matemáticas está triste?",
            )

        assert len(notes) == 1
        assert notes[0].note == "Usa humor constante"

    @pytest.mark.asyncio
    async def test_evolve_returns_empty_on_exception(self, mock_llm: MagicMock) -> None:
        chain = PersonaEvolutionChain(llm=mock_llm)

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(side_effect=RuntimeError("LLM failure"))
            notes = await chain.evolve(
                user_message="Hola",
                assistant_response="Hola",
            )

        assert notes == []

    @pytest.mark.asyncio
    async def test_evolve_passes_prior_persona_to_chain(self, mock_llm: MagicMock) -> None:
        chain = PersonaEvolutionChain(llm=mock_llm)
        empty = PersonaNotes(notes=[])

        with patch.object(chain, "chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(return_value=empty)
            await chain.evolve(
                user_message="...",
                assistant_response="...",
                prior_persona=["Ya tiene un tono directo establecido"],
            )
            call_args = mock_chain.ainvoke.call_args[0][0]
            assert "Ya tiene un tono directo establecido" in call_args["prior_persona"]
