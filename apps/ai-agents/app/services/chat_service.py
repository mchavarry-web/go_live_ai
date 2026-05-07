"""Chat service orchestrating LangChain components for response generation.

Coordinates AvatarChain, InsightExtractionChain, PersonaEvolutionChain, and
MemoryService to produce avatar responses with memory. Handles both complete
and streamed generation modes. All LLM calls are traced via LangSmith.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langsmith import traceable
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _get_async_session_maker
from app.chains.avatar_chain import AvatarChain
from app.chains.correction_detector_chain import CorrectionDetectorChain
# EventExtractionChain is no longer instantiated here — EventService owns
# the extract+persist pipeline and builds its own chain per invocation.
from app.chains.insight_chain import InsightExtractionChain
from app.chains.persona_evolution_chain import PersonaEvolutionChain
from app.chains.slang_calibrator_chain import SlangCalibratorChain
from app.config.settings import Settings
from app.models.enums import InsightCategory
from app.models.schemas import (
    ChatGenerateRequest,
    ChatGenerateResponse,
    Insight,
    ProactiveGenerateRequest,
    ProactiveGenerateResponse,
    UserEvent,
)
from app.prompts.event_humanizer import serialize_events_for_prompt
from app.prompts.proactive_greeting import build_proactive_system_prompt
from app.repositories.audio_transcript_repository import AudioTranscriptRepository
from app.repositories.event_repository import EventRepository
from app.repositories.user_style_profile_repository import UserStyleProfileRepository
from app.services.conversation_summary_service import ConversationSummaryService
from app.services.event_service import EventService
from app.services.memory_service import MemoryService
from app.services.search_engagement_service import (
    SearchContext,
    SearchEngagementService,
    bind_chat_request,
    take_prior_search_for,
)

_DEFAULT_TIMEZONE = "America/Lima"
_UPCOMING_EVENTS_HORIZON_DAYS = 14
_UPCOMING_EVENTS_LIMIT = 10

# Wave A.2 (2026-05-06) — cosine-distance ceilings for chat-time insight
# retrieval. `text-embedding-3-small` cosine distance distributions place
# topical-but-only-loosely-related rows around 0.40–0.50, so we cap at 0.40
# for user facts (we don't want a stale `health` insight surfacing when
# the user is asking about work) and a slightly looser 0.45 for persona
# notes (which are paraphrased and naturally land further from the query).
_USER_INSIGHT_MAX_DISTANCE = 0.40
_PERSONA_INSIGHT_MAX_DISTANCE = 0.45

# Strict ceiling for pre-insert dedupe lookups (Wave A.3). At ~0.15 cosine
# distance, content is essentially the same paraphrased — the canonical
# "user likes coffee" / "user enjoys coffee" pair lands at 0.10–0.13. We
# keep the bar tight to avoid suppressing genuinely new nuance.
_INSIGHT_DEDUPE_MAX_DISTANCE = 0.15

# Phase 13 history truncation: when a prior summary covers everything older
# than this tail, the chat-time prompt only sends the last N entries to the
# avatar. The summary picks up the slack as medium-term memory.
_SUMMARY_KEEP_TAIL_ENTRIES = 10
_SUMMARY_TRUNCATE_THRESHOLD = 20


def _maybe_truncate_history(
    conversation_history: list[dict[str, str]] | None,
    *,
    prior_summary: str | None,
) -> list[dict[str, str]] | None:
    """Trim conversation history to the last N entries when a summary covers the rest.

    Truncation only kicks in when both:
    - a non-empty ``prior_summary`` exists (so older context isn't lost), AND
    - the history is longer than ``_SUMMARY_TRUNCATE_THRESHOLD``.
    Otherwise return the input unchanged.
    """
    if not conversation_history or not prior_summary:
        return conversation_history
    if len(conversation_history) <= _SUMMARY_TRUNCATE_THRESHOLD:
        return conversation_history
    return conversation_history[-_SUMMARY_KEEP_TAIL_ENTRIES:]

_SLANG_CALIBRATION_INTERVAL = 5

logger = logging.getLogger(__name__)


class ChatService:
    """Service that orchestrates avatar chat response generation with memory.

    Creates an ``AvatarChain``, ``InsightExtractionChain``, and
    ``PersonaEvolutionChain``, and delegates message generation to them.
    Retrieves relevant insights and persona notes from MemoryService before
    generating, and stores new ones after generating.

    Attributes:
        avatar_chain: The underlying LangChain avatar chain.
        insight_chain: The chain for extracting insights from messages.
        persona_chain: The chain for evolving the avatar's persona notes.
        settings: Application configuration.
        llm: The LangChain LLM instance.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        settings: Settings,
        embeddings: Optional[Embeddings] = None,
    ) -> None:
        """Initialize the chat service.

        Args:
            llm: A LangChain BaseChatModel instance.
            settings: Application settings for configuration.
            embeddings: Optional LangChain Embeddings instance for memory.
        """
        self.avatar_chain = AvatarChain(llm=llm, settings=settings)
        self.insight_chain = InsightExtractionChain(llm=llm)
        self.persona_chain = PersonaEvolutionChain(llm=llm)
        self.slang_calibrator = SlangCalibratorChain(llm=llm)
        self.correction_detector = CorrectionDetectorChain(llm=llm)
        self.settings = settings
        self.llm = llm
        self.embeddings = embeddings

    def _extract_user_profile(
        self,
        request: ChatGenerateRequest,
        insights: list[str] | None = None,
        persona_insights: list[str] | None = None,
        formality_level: float | None = None,
        custom_expressions: list[str] | None = None,
        upcoming_events: list | None = None,
        prior_summary: str | None = None,
        transcript_quotes: list[str] | None = None,
    ) -> dict:
        """Extract user profile dict from the API request.

        Combines data from ``request.user_profile``, ``request.social_data``,
        ``request.health_data``, memory insights, avatar persona notes, and
        language style data into a single dict for the chain.

        Args:
            request: The incoming chat generation request.
            insights: Optional list of user insight strings from memory.
            persona_insights: Optional list of avatar persona evolution notes.
            formality_level: Detected formality from language style insights.
            custom_expressions: Detected custom expressions from the user.

        Returns:
            A dict containing all profile and context data for prompt building.
        """
        profile = request.user_profile
        tz = profile.timezone or _DEFAULT_TIMEZONE
        events_payload = serialize_events_for_prompt(
            upcoming_events or [],
            user_tz=tz,
            now_utc=datetime.now(UTC),
        )
        return {
            "avatar_name": profile.avatar_name,
            "display_name": profile.display_name,
            "knowledge_level": profile.knowledge_level,
            "age_range": profile.age_range,
            "country": profile.country,
            "timezone": profile.timezone,
            "interests": list(profile.interests),
            "introvert_extrovert": profile.introvert_extrovert,
            "rational_emotional": profile.rational_emotional,
            "values": list(profile.values) if profile.values else None,
            "behavior_settings": dict(profile.behavior_settings) if profile.behavior_settings else None,
            "social_data": dict(request.social_data) if request.social_data else None,
            "health_data": dict(request.health_data) if request.health_data else None,
            "last_location": dict(profile.last_location) if profile.last_location else None,
            "insights": insights,
            "persona_insights": persona_insights,
            "formality_level": formality_level,
            "custom_expressions": custom_expressions,
            "upcoming_events": events_payload,
            "prior_summary": prior_summary,
            "transcript_quotes": transcript_quotes or [],
            "active_mode": profile.active_mode,
            "mode_message_count": profile.mode_message_count,
        }

    async def _get_memory_insights(
        self,
        user_id: str,
        message: str,
        session: Optional[AsyncSession] = None,
    ) -> list[str] | None:
        """Retrieve relevant user insights from memory (excludes avatar_evolution).

        Args:
            user_id: The user's unique identifier.
            message: The user's message to find relevant context for.
            session: Optional database session for memory operations.

        Returns:
            List of insight content strings, or None if memory is not available.
        """
        if not session or not self.embeddings:
            return None

        _excluded = {InsightCategory.AVATAR_EVOLUTION, InsightCategory.LANGUAGE_STYLE}
        user_categories = [
            cat.value for cat in InsightCategory if cat not in _excluded
        ]

        try:
            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            relevant = await memory_service.get_relevant_insights(
                user_id=user_id,
                query=message,
                top_k=10,
                categories=user_categories,
                max_distance=_USER_INSIGHT_MAX_DISTANCE,
            )
            if relevant:
                return [ins.content for ins in relevant]
            return None
        except Exception:
            logger.warning(
                "Failed to retrieve memory insights for user_id=%s",
                user_id,
                exc_info=True,
            )
            return None

    async def _get_persona_insights(
        self,
        user_id: str,
        message: str,
        session: Optional[AsyncSession] = None,
        active_mode: str = "friends",
    ) -> list[str] | None:
        """Retrieve the avatar's persona evolution notes for this user.

        Persona evolution is mode-scoped: notes written by the chain carry
        ``source = "persona_update:<mode>"``. We push the source filter into
        the SQL ``WHERE`` clause so the cosine-distance ``LIMIT`` only sees
        matching rows — otherwise a user with many notes in one mode would
        crowd out the active mode at the top-k stage.

        Back-compat: rows written before mode support carry the bare
        ``persona_update`` source. Those surface only when the active mode
        is ``friends`` (the historical default).

        Args:
            user_id: The user's unique identifier.
            message: The current message, used for semantic relevance ranking.
            session: Optional database session.
            active_mode: Current avatar mode; persona pool is filtered to it.

        Returns:
            List of persona note strings, or None if memory is not available.
        """
        if not session or not self.embeddings:
            return None

        try:
            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            allowed_sources = [f"persona_update:{active_mode}"]
            if active_mode == "friends":
                # Legacy rows written before mode support default to friends.
                allowed_sources.append("persona_update")

            relevant = await memory_service.get_relevant_insights(
                user_id=user_id,
                query=message,
                top_k=5,
                categories=[InsightCategory.AVATAR_EVOLUTION.value],
                sources=allowed_sources,
                max_distance=_PERSONA_INSIGHT_MAX_DISTANCE,
            )
            if not relevant:
                return None

            return [ins.content for ins in relevant]
        except Exception:
            logger.warning(
                "Failed to retrieve persona insights for user_id=%s",
                user_id,
                exc_info=True,
            )
            return None

    async def _get_relevant_transcript_quotes(
        self,
        user_id: str,
        message: str,
        session: Optional[AsyncSession] = None,
    ) -> list[str]:
        """Semantic search over the user's audio-transcript chunk pool (Phase 14).

        Distinct from ``_get_memory_insights`` which retrieves derived
        summaries; this returns verbatim quotes from what the user said
        in their journal/recordings. Used for "what did I say about X"
        type avatar context. Strict cosine threshold (0.25) keeps
        tangentially-related quotes from leaking in.

        Returns at most 3 quote strings, or [] when no embedding provider,
        no session, no qualifying matches, or any error.
        """
        if not session or not self.embeddings:
            return []
        try:
            query_embedding = await self.embeddings.aembed_query(message)
        except Exception:
            logger.warning(
                "transcript-quote query embedding failed user_id=%s",
                user_id,
                exc_info=True,
            )
            return []
        try:
            repo = AudioTranscriptRepository(session)
            rows = await repo.search_similar(
                user_id,
                query_embedding,
                top_k=3,
                max_distance=0.25,
            )
            return [row.text for row in rows if row.text]
        except Exception:
            logger.warning(
                "Failed to retrieve transcript quotes user_id=%s",
                user_id,
                exc_info=True,
            )
            return []

    async def _get_prior_summary(
        self,
        conversation_id: str | None,
        session: Optional[AsyncSession] = None,
    ) -> str | None:
        """Fetch the latest non-superseded summary for the conversation.

        Falls back to None on missing session, missing conversation_id, or
        repository error — the prompt builder simply omits the section.
        """
        if not session or not conversation_id:
            return None
        try:
            return await ConversationSummaryService(session).latest_summary_text(
                conversation_id
            )
        except Exception:
            logger.warning(
                "Failed to fetch prior summary for conversation_id=%s",
                conversation_id,
                exc_info=True,
            )
            return None

    async def _get_upcoming_events(
        self,
        user_id: str,
        session: Optional[AsyncSession] = None,
    ) -> list:
        """Fetch upcoming events for prompt injection (filter-by-time, no RAG).

        Also performs an opportunistic archive of past events for the same
        user — keeps the read window clean without a cron job. Failures
        always degrade to an empty list so an event-table outage cannot
        break chat generation.

        Args:
            user_id: The user's unique identifier.
            session: Optional database session.

        Returns:
            List of ``UserEventModel`` rows occurring within the next
            ``_UPCOMING_EVENTS_HORIZON_DAYS``, soonest first. Empty when
            no session, no events, or on error.
        """
        if not session:
            return []

        try:
            repo = EventRepository(session)
            now_utc = datetime.now(UTC)
            await repo.archive_past(user_id, before=now_utc)
            return await repo.list_upcoming(
                user_id,
                now_utc=now_utc,
                horizon_days=_UPCOMING_EVENTS_HORIZON_DAYS,
                limit=_UPCOMING_EVENTS_LIMIT,
            )
        except Exception:
            logger.warning(
                "Failed to retrieve upcoming events for user_id=%s",
                user_id,
                exc_info=True,
            )
            return []

    async def _get_language_style(
        self,
        user_id: str,
        session: Optional[AsyncSession] = None,
    ) -> tuple[float | None, list[str] | None]:
        """Retrieve the user's language style profile.

        Wave B.3 (2026-05-06) — prefer the structured ``user_style_profiles``
        row when present; fall back to the legacy JSON-blob `language_style`
        insight so older users without a structured row still get prompt
        personalization.

        Args:
            user_id: The user's unique identifier.
            session: Optional database session.

        Returns:
            Tuple of (formality_level, custom_expressions). Both may be
            None if no style data exists.
        """
        if not session:
            return None, None

        # Prefer the typed table.
        try:
            profile = await UserStyleProfileRepository(session).get_for_user(user_id)
        except Exception:
            profile = None
            logger.warning(
                "Failed to fetch user style profile for user_id=%s — falling back",
                user_id,
                exc_info=True,
            )
        if profile is not None and (profile.formality_level is not None or profile.custom_expressions):
            return profile.formality_level, profile.custom_expressions or None

        if not self.embeddings:
            return None, None
        try:
            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            relevant = await memory_service.get_relevant_insights(
                user_id=user_id,
                query="language style formality slang",
                top_k=1,
                categories=[InsightCategory.LANGUAGE_STYLE.value],
            )
            if relevant:
                return SlangCalibratorChain.parse_insight_content(
                    relevant[0].content
                )
            return None, None
        except Exception:
            logger.warning(
                "Failed to retrieve language style for user_id=%s",
                user_id,
                exc_info=True,
            )
            return None, None

    async def _calibrate_and_store_slang(
        self,
        user_id: str,
        conversation_history: list[dict[str, str]] | None,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Run the slang calibrator and store the result as a language_style insight.

        Only runs if there are enough user messages in the history.
        Failures are logged but never propagate.

        Args:
            user_id: The user's unique identifier.
            conversation_history: Recent messages as role/content dicts.
            session: Optional database session.
        """
        if not session or not self.embeddings or not conversation_history:
            return

        user_messages = [
            entry["content"]
            for entry in conversation_history
            if entry.get("role", "").lower() == "user" and entry.get("content")
        ]

        if len(user_messages) < 2:
            return

        try:
            profile = await self.slang_calibrator.calibrate(user_messages)
            if not profile:
                return

            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            # Wave B.3 — also write the structured profile row. Reads
            # prefer this table; the legacy insight write below is kept
            # for back-compat until the table fully replaces it.
            try:
                await UserStyleProfileRepository(session).upsert_core(
                    user_id=user_id,
                    formality_level=profile.formality_level,
                    custom_expressions=profile.custom_expressions,
                    emoji_frequency=profile.emoji_frequency,
                )
            except Exception:
                logger.warning(
                    "Failed to upsert user_style_profile for user_id=%s — "
                    "legacy insight will still be written",
                    user_id,
                    exc_info=True,
                )
            # dedupe=False — language_style content is a JSON blob whose
            # cosine distance is dominated by the JSON shape, not by the
            # actual style values. Two calibrations with different
            # formality readings would falsely register as near-dupes.
            # Slang is overwrite-style memory anyway (latest wins).
            await memory_service.store_insights(
                user_id=user_id,
                insights=[
                    {
                        "category": InsightCategory.LANGUAGE_STYLE.value,
                        "content": SlangCalibratorChain.profile_to_insight_content(
                            profile
                        ),
                        "confidence": 0.8,
                    }
                ],
                source="slang_calibration",
                dedupe=False,
            )
            logger.info(
                "Stored slang calibration for user_id=%s: formality=%.2f",
                user_id,
                profile.formality_level,
            )
        except Exception:
            logger.exception(
                "Slang calibration failed for user_id=%s — skipping",
                user_id,
            )

    async def _evolve_and_store_persona(
        self,
        user_id: str,
        user_message: str,
        assistant_response: str,
        prior_persona: list[str] | None,
        session: Optional[AsyncSession] = None,
        active_mode: str = "friends",
    ) -> None:
        """Run the persona evolution chain and store resulting notes.

        Persona notes are mode-scoped — the source string ``persona_update:<mode>``
        ensures Profesional voice doesn't leak into Citas (and vice-versa) on
        retrieval.

        Failures are logged but never propagate — this must not affect response
        delivery.

        Args:
            user_id: The user's unique identifier.
            user_message: The user's message in this turn.
            assistant_response: The avatar's reply in this turn.
            prior_persona: Existing persona notes for context.
            session: Optional database session.
            active_mode: Current avatar mode; scopes the source string.
        """
        if not session or not self.embeddings:
            return

        try:
            notes = await self.persona_chain.evolve(
                user_message=user_message,
                assistant_response=assistant_response,
                prior_persona=prior_persona,
            )
            if not notes:
                return

            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            await memory_service.store_insights(
                user_id=user_id,
                insights=[
                    {
                        "category": InsightCategory.AVATAR_EVOLUTION.value,
                        "content": note.note,
                        "confidence": note.confidence,
                    }
                    for note in notes
                ],
                source=f"persona_update:{active_mode}",
            )
            logger.info(
                "Stored %d persona evolution notes for user_id=%s mode=%s",
                len(notes),
                user_id,
                active_mode,
            )
        except Exception:
            logger.exception(
                "Persona evolution storage failed for user_id=%s — skipping",
                user_id,
            )

    async def _extract_and_store_insights(
        self,
        user_id: str,
        message: str,
        existing_insights: list[str] | None,
        session: Optional[AsyncSession] = None,
        assistant_response: Optional[str] = None,
    ) -> list[Insight]:
        """Extract insights from the conversation turn and store them.

        Runs asynchronously after response generation. Does not block
        the response. Failures are logged but do not affect the chat.

        Args:
            user_id: The user's unique identifier.
            message: The user's message to extract insights from.
            existing_insights: Existing insight strings for context.
            session: Optional database session for memory operations.
            assistant_response: The avatar's reply for this turn, used to
                capture confirmations or implicit agreements.

        Returns:
            List of Insight schemas for the newly extracted insights.
        """
        if not session or not self.embeddings:
            return []

        try:
            context = ""
            if existing_insights:
                context = "Insights previos: " + "; ".join(existing_insights)

            extracted = await self.insight_chain.extract(
                message=message,
                context=context,
                assistant_response=assistant_response,
            )

            if not extracted:
                return []

            # Store in memory
            memory_service = MemoryService(
                session=session,
                embeddings=self.embeddings,
            )
            insight_dicts = [
                {
                    "category": ins.category,
                    "content": ins.content,
                    "confidence": ins.confidence,
                }
                for ins in extracted
            ]

            stored = await memory_service.store_insights(
                user_id=user_id,
                insights=insight_dicts,
                source="conversation",
            )

            # Convert to API schemas
            return [
                Insight(
                    id=ins.id,
                    user_id=ins.user_id,
                    category=ins.category,
                    content=ins.content,
                    confidence=ins.confidence,
                    source=ins.source,
                    created_at=ins.created_at,
                )
                for ins in stored
            ]

        except Exception:
            logger.exception(
                "Insight extraction/storage failed for user_id=%s",
                user_id,
            )
            return []

    async def _detect_and_apply_corrections(
        self,
        *,
        user_id: str,
        message: str,
        session: Optional[AsyncSession],
    ) -> int:
        """Wave B.1 — detect retractions and supersede matching insights.

        Runs FIRST in the post-turn batch so insight extraction doesn't
        re-extract a fact the user just retracted. Always best-effort:
        failures yield 0 superseded and never block the chat flow.
        """
        if not session or not self.embeddings:
            return 0
        try:
            signals = await self.correction_detector.detect(message)
        except Exception:
            logger.exception(
                "Correction detection chain failed user_id=%s — skipping",
                user_id,
            )
            return 0
        if not signals:
            return 0
        memory_service = MemoryService(session=session, embeddings=self.embeddings)
        try:
            return await memory_service.apply_corrections(user_id, signals)
        except Exception:
            logger.exception(
                "Correction application failed user_id=%s — skipping",
                user_id,
            )
            return 0

    async def _extract_and_store_events(
        self,
        *,
        user_id: str,
        message: str,
        timezone: str | None,
        message_created_at: datetime | None,
        session: Optional[AsyncSession],
        assistant_response: Optional[str] = None,
    ) -> list[UserEvent]:
        """Extract dated commitments from the chat turn and persist them.

        Thin wrapper around ``EventService.extract_and_store_from_text`` so
        chat / audio / social ingest all share the same dedupe loop and
        confidence floor. Source is always ``"conversation"``.

        Args:
            user_id: The user's unique identifier.
            message: The user's message text.
            timezone: IANA tz name (``"America/Lima"`` fallback).
            message_created_at: When the user sent the message (UTC).
                Falls back to "now" if missing.
            session: Optional database session.
            assistant_response: Optional assistant turn text used by the
                chain to capture confirmations.

        Returns:
            List of newly persisted ``UserEvent`` schemas.
        """
        if not session:
            return []
        return await EventService(session).extract_and_store_from_text(
            llm=self.llm,
            user_id=user_id,
            text=message,
            source="conversation",
            timezone=timezone,
            anchor_at=message_created_at,
            assistant_response=assistant_response,
        )

    @traceable(name="generate_chat_response", run_type="chain")
    async def generate_response(
        self,
        request: ChatGenerateRequest,
        session: Optional[AsyncSession] = None,
    ) -> ChatGenerateResponse:
        """Generate a complete avatar response with memory context.

        1. Retrieves relevant insights from memory.
        2. Generates the avatar response using AvatarChain.
        3. Extracts new insights from the user's message.
        4. Stores new insights in the vector database.

        Args:
            request: The chat generation request with message and context.
            session: Optional database session for memory operations.

        Returns:
            A ChatGenerateResponse with the avatar's reply and metadata.

        Raises:
            Exception: Propagates any LLM or chain errors.
        """
        logger.info(
            "Generating chat response: user_id=%s, conversation_id=%s",
            request.user_id,
            request.conversation_id,
        )

        # Bind the request identity so any web_search tool calls during
        # this turn can stash their query into the engagement-cache
        # without needing user/conv args plumbed through the agent.
        bind_chat_request(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

        # Capture any prior turn's search context BEFORE the agent runs
        # this turn — otherwise a fresh stash would overwrite it.
        prior_search = await take_prior_search_for(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

        # Step 1: Retrieve all memory context in parallel
        mem = await _gather_memory(
            self,
            request.user_id,
            request.message,
            session,
            active_mode=request.user_profile.active_mode,
            conversation_id=request.conversation_id,
        )

        # Step 2: Build user profile with memory context
        user_profile = self._extract_user_profile(
            request,
            insights=mem.memory_insights,
            persona_insights=mem.persona_insights,
            formality_level=mem.formality_level,
            custom_expressions=mem.custom_expressions,
            upcoming_events=mem.upcoming_events,
            prior_summary=mem.prior_summary,
            transcript_quotes=mem.transcript_quotes,
        )

        # Step 3: Generate response. When a prior summary is in play, the
        # tail-only history slice keeps the prompt token budget bounded.
        history_for_chain = _maybe_truncate_history(
            request.conversation_history,
            prior_summary=mem.prior_summary,
        )
        try:
            result = await self.avatar_chain.generate(
                message=request.message,
                user_profile=user_profile,
                conversation_history=history_for_chain or None,
            )
        except Exception:
            logger.exception(
                "Chat generation failed: user_id=%s, conversation_id=%s",
                request.user_id,
                request.conversation_id,
            )
            raise

        logger.info(
            "Chat response generated: user_id=%s, tokens_used=%d",
            request.user_id,
            result["tokens_used"],
        )

        # Step 4: Post-turn memory updates in parallel (non-blocking, independent)
        history = request.conversation_history or []
        turn_count = sum(1 for e in history if e.get("role") == "user")
        should_calibrate = turn_count > 0 and turn_count % _SLANG_CALIBRATION_INTERVAL == 0

        # Step 4a (Wave B.1): apply corrections FIRST so insight extraction
        # below doesn't re-add facts the user just retracted.
        await self._detect_and_apply_corrections(
            user_id=request.user_id,
            message=request.message,
            session=session,
        )

        post_turn_tasks = [
            self._extract_and_store_insights(
                user_id=request.user_id,
                message=request.message,
                existing_insights=mem.memory_insights,
                session=session,
                assistant_response=result["response"],
            ),
            self._evolve_and_store_persona(
                user_id=request.user_id,
                user_message=request.message,
                assistant_response=result["response"],
                prior_persona=mem.persona_insights,
                session=session,
                active_mode=request.user_profile.active_mode,
            ),
            self._extract_and_store_events(
                user_id=request.user_id,
                message=request.message,
                timezone=request.user_profile.timezone,
                message_created_at=request.message_created_at,
                session=session,
                assistant_response=result["response"],
            ),
        ]
        if should_calibrate:
            post_turn_tasks.append(
                self._calibrate_and_store_slang(
                    user_id=request.user_id,
                    conversation_history=history,
                    session=session,
                )
            )
        if prior_search is not None and self.embeddings:
            post_turn_tasks.append(
                SearchEngagementService(
                    session=session, embeddings=self.embeddings
                ).maybe_capture(
                    llm=self.llm,
                    user_id=request.user_id,
                    conversation_id=request.conversation_id,
                    user_message=request.message,
                    prior_search=prior_search,
                )
            )

        gather_results = await asyncio.gather(*post_turn_tasks, return_exceptions=True)
        insights_result = gather_results[0]
        new_insights = insights_result if isinstance(insights_result, list) else []

        return ChatGenerateResponse(
            response=result["response"],
            tokens_used=result["tokens_used"],
            new_insights=new_insights,
        )

    async def _fetch_news_context(self, request: ProactiveGenerateRequest) -> dict[str, str]:
        """Search for recent news via Tavily based on the user's interests.

        Picks up to 3 interests using a rotating selection so different topics
        are covered across sessions. The rotation seed combines the user ID and
        the local date, producing a stable selection within the same day but a
        different one each new day (or each new session when absence_minutes varies).

        Degrades gracefully: if Tavily is not configured or the search fails,
        returns an empty dict so the greeting falls back to generic behaviour.

        Args:
            request: The proactive greeting request (used for user interests).

        Returns:
            Dict with ``"news_results"`` key containing formatted news snippets,
            or empty dict on failure.
        """
        import random as _random

        tavily_key = self.settings.tavily_api_key.get_secret_value() if self.settings.tavily_api_key else ""
        if not tavily_key:
            logger.warning(
                "No TAVILY_API_KEY configured — news skill will fall back to generic greeting"
            )
            return {}

        interests = request.user_profile.interests or []
        if not interests:
            logger.info(
                "User %s has no interests set — skipping news search", request.user_id
            )
            return {}

        # Rotate which interests are used each session.
        # Seed = user_id + local_date so the selection is stable within the same
        # calendar day but shifts daily (and also shifts when absence_minutes changes,
        # giving extra variety across multiple opens in the same day).
        seed = f"{request.user_id}:{request.local_date}:{request.absence_minutes}"
        rng = _random.Random(seed)
        selected = rng.sample(interests, k=min(3, len(interests)))

        query_topics = ", ".join(selected)
        query = f"latest news about {query_topics}"

        logger.info(
            "Fetching news for proactive greeting: user_id=%s, query=%r",
            request.user_id,
            query,
        )

        try:
            from langchain_tavily import TavilySearch

            tavily = TavilySearch(
                max_results=3,
                tavily_api_key=tavily_key,
                search_depth="basic",
                include_answer=True,
                include_raw_content=False,
                include_images=False,
                topic="news",
            )
            raw = await tavily.ainvoke(query)

            lines: list[str] = []
            if isinstance(raw, dict):
                if raw.get("answer"):
                    lines.append(f"Summary: {raw['answer']}")
                for item in (raw.get("results") or []):
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title", "")
                    snippet = (item.get("content") or item.get("snippet") or "")[:250]
                    url = item.get("url", "")
                    if title:
                        lines.append(f"- {title}: {snippet} ({url})")

            news_text = "\n".join(lines).strip()
            if not news_text:
                logger.info("Tavily returned no usable news results for query %r", query)
                return {}

            logger.info(
                "News context fetched: user_id=%s, results=%d chars",
                request.user_id,
                len(news_text),
            )
            return {"news_results": news_text}

        except Exception:
            logger.exception(
                "Tavily news search failed for user_id=%s, query=%r — degrading to generic greeting",
                request.user_id,
                query,
            )
            return {}

    @traceable(name="generate_proactive_greeting", run_type="chain")
    async def generate_proactive_greeting(
        self,
        request: ProactiveGenerateRequest,
        session: Optional[AsyncSession] = None,
    ) -> ProactiveGenerateResponse:
        """Generate a proactive avatar greeting for when the user returns to the app.

        Unlike generate_response (which reacts to a user message), this method
        has the avatar speak first. It uses a purpose-built system prompt and
        invokes the LLM directly without the full AvatarChain pipeline.

        For the ``news`` skill, Tavily is called first to fetch recent headlines
        about the user's interests. The results are injected into ``skill_context``
        before building the system prompt. If Tavily is unavailable or fails, the
        greeting degrades gracefully to a generic greeting.

        Args:
            request: The proactive greeting request with skill and user context.
            session: Optional database session (reserved for future skill memory).

        Returns:
            ProactiveGenerateResponse with the generated greeting text.

        Raises:
            Exception: Propagates any LLM errors.
        """
        logger.info(
            "Generating proactive greeting: user_id=%s, skill=%s, absence=%dmin",
            request.user_id,
            request.skill_id,
            request.absence_minutes,
        )

        # Enrich request with news context when the news skill is selected.
        # If the search fails or returns nothing, news_context will be empty and
        # the prompt will behave identically to the generic_greeting skill.
        enriched_request = request
        if request.skill_id == "news":
            news_context = await self._fetch_news_context(request)
            enriched_request = request.model_copy(
                update={"skill_context": {**request.skill_context, **news_context}}
            )

        system_prompt = build_proactive_system_prompt(enriched_request)

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="[Inicia el saludo]"),
            ]
            result = await self.llm.ainvoke(messages)
            greeting = result.content if hasattr(result, "content") else str(result)

            usage = getattr(result, "usage_metadata", None) or getattr(result, "response_metadata", {})
            tokens_used = (
                usage.get("total_tokens", 0)
                if isinstance(usage, dict)
                else 0
            )

        except Exception:
            logger.exception(
                "Proactive greeting generation failed: user_id=%s, skill=%s",
                request.user_id,
                request.skill_id,
            )
            raise

        logger.info(
            "Proactive greeting generated: user_id=%s, skill=%s, tokens=%d",
            request.user_id,
            request.skill_id,
            tokens_used,
        )

        return ProactiveGenerateResponse(
            greeting=greeting,
            emotion=None,
            skill_used=request.skill_id,
            tokens_used=tokens_used,
        )

    @traceable(name="generate_chat_stream", run_type="chain")
    async def generate_stream(
        self,
        request: ChatGenerateRequest,
        session: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream avatar response tokens in SSE format with memory context.

        Each yielded string is a Server-Sent Event (SSE) formatted line
        containing a JSON payload with the token chunk. A final ``[DONE]``
        event signals stream completion.

        Args:
            request: The chat generation request with message and context.
            session: Optional database session for memory operations.

        Yields:
            SSE-formatted strings: ``data: {"token": "..."}\\n\\n``
            and a final ``data: [DONE]\\n\\n``.
        """
        # Hop-by-hop telemetry — emitted as the penultimate SSE frame so
        # Rails can stitch it into the assistant Message metadata. Even on
        # exception we still emit what we have (Rails persists partial logs
        # so testers can spot which leg of the trip stalled).
        from datetime import datetime, timezone

        def _now_iso() -> str:
            return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        ai_received_at = _now_iso()

        # Bind for search-engagement stash (Phase 15).
        bind_chat_request(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )
        prior_search = await take_prior_search_for(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
        )

        # Retrieve memory context
        mem = await _gather_memory(
            self,
            request.user_id,
            request.message,
            session,
            active_mode=request.user_profile.active_mode,
            conversation_id=request.conversation_id,
        )

        user_profile = self._extract_user_profile(
            request,
            insights=mem.memory_insights,
            persona_insights=mem.persona_insights,
            formality_level=mem.formality_level,
            custom_expressions=mem.custom_expressions,
            upcoming_events=mem.upcoming_events,
            prior_summary=mem.prior_summary,
            transcript_quotes=mem.transcript_quotes,
        )

        history_for_stream = _maybe_truncate_history(
            request.conversation_history,
            prior_summary=mem.prior_summary,
        )

        logger.info(
            "Starting streaming chat response: user_id=%s, conversation_id=%s",
            request.user_id,
            request.conversation_id,
        )

        streamed_tokens: list[str] = []
        ai_first_token_at: Optional[str] = None
        try:
            async for token in self.avatar_chain.generate_stream(
                message=request.message,
                user_profile=user_profile,
                conversation_history=history_for_stream or None,
            ):
                if ai_first_token_at is None and token:
                    ai_first_token_at = _now_iso()
                streamed_tokens.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception:
            logger.exception(
                "Chat streaming failed: user_id=%s, conversation_id=%s",
                request.user_id,
                request.conversation_id,
            )
            error_payload = json.dumps(
                {"error": "Stream generation failed"}, ensure_ascii=False
            )
            yield f"data: {error_payload}\n\n"

        ai_last_token_at = _now_iso()
        ai_to_api_done_at = _now_iso()

        telemetry = {
            "ai_received_at":     ai_received_at,
            "ai_first_token_at":  ai_first_token_at,
            "ai_last_token_at":   ai_last_token_at,
            "ai_to_api_done_at":  ai_to_api_done_at,
        }
        yield f"data: {json.dumps({'telemetry': telemetry}, ensure_ascii=False)}\n\n"

        # Schedule post-turn memory work as a true background task with its
        # own DB session, then yield [DONE] and return immediately so Rails'
        # streaming HTTP connection closes ASAP. Without this, Rails waits
        # 5–10s for insight extraction + persona evolution before broadcasting
        # the assistant message — which made the chat input look frozen.
        full_response = "".join(streamed_tokens) or None
        history = request.conversation_history or []
        turn_count = sum(1 for e in history if e.get("role") == "user")
        should_calibrate = turn_count > 0 and turn_count % _SLANG_CALIBRATION_INTERVAL == 0

        # Wave B.4 — post-turn learning has two execution modes:
        #   - Inline (legacy, default): asyncio.create_task fires-and-forgets.
        #     Fast, but lost on worker restart.
        #   - Durable: Rails enqueues a Sidekiq job after the assistant
        #     Message is persisted that calls /internal/chat/learn.
        # The flag toggles only the inline kick; the durable path is
        # always reachable via the public endpoint.
        if self.settings.post_turn_inline:
            asyncio.create_task(
                self._run_post_turn_tasks(
                    user_id=request.user_id,
                    user_message=request.message,
                    assistant_response=full_response,
                    memory_insights=mem.memory_insights,
                    persona_insights=mem.persona_insights,
                    conversation_history=history,
                    should_calibrate=should_calibrate,
                    active_mode=request.user_profile.active_mode,
                    timezone=request.user_profile.timezone,
                    message_created_at=request.message_created_at,
                    conversation_id=request.conversation_id,
                    display_name=request.user_profile.display_name,
                    turn_count=turn_count,
                    prior_search=prior_search,
                )
            )

        yield "data: [DONE]\n\n"

    async def learn(
        self,
        *,
        session: AsyncSession,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_response: str | None,
        conversation_history: list[dict[str, str]],
        active_mode: str = "friends",
        display_name: str = "el usuario",
        turn_count: int = 0,
        timezone: str | None = None,
        message_created_at: datetime | None = None,
    ) -> dict[str, int | bool]:
        """Wave B.4 — durable post-turn learning entrypoint.

        Used by the ``/internal/chat/learn`` HTTP endpoint when Rails owns
        durability via Sidekiq. Re-fetches the memory pools the
        in-process path captured during ``generate_stream`` so the chains
        have the same context.

        Returns a dict of counts safe to persist on the assistant Message
        metadata for observability.
        """
        import time

        t0 = time.perf_counter()
        # Re-derive the gather-memory pools so chains have prior context.
        try:
            mem_insights = await self._get_memory_insights(
                user_id=user_id, message=user_message, session=session
            )
        except Exception:
            mem_insights = None
        try:
            persona_insights = await self._get_persona_insights(
                user_id=user_id,
                message=user_message,
                session=session,
                active_mode=active_mode,
            )
        except Exception:
            persona_insights = None

        # Apply corrections first.
        superseded = await self._detect_and_apply_corrections(
            user_id=user_id, message=user_message, session=session
        )

        should_calibrate = (
            turn_count > 0 and turn_count % _SLANG_CALIBRATION_INTERVAL == 0
        )
        prior_search = await take_prior_search_for(
            user_id=user_id, conversation_id=conversation_id
        )

        tasks = [
            self._extract_and_store_insights(
                user_id=user_id,
                message=user_message,
                existing_insights=mem_insights,
                session=session,
                assistant_response=assistant_response,
            ),
            self._evolve_and_store_persona(
                user_id=user_id,
                user_message=user_message,
                assistant_response=assistant_response or "",
                prior_persona=persona_insights,
                session=session,
                active_mode=active_mode,
            ),
            self._extract_and_store_events(
                user_id=user_id,
                message=user_message,
                timezone=timezone,
                message_created_at=message_created_at,
                session=session,
                assistant_response=assistant_response,
            ),
        ]
        if should_calibrate:
            tasks.append(
                self._calibrate_and_store_slang(
                    user_id=user_id,
                    conversation_history=conversation_history,
                    session=session,
                )
            )
        if conversation_id and ConversationSummaryService.should_summarize(
            turn_count=turn_count
        ):
            tasks.append(
                ConversationSummaryService(session).summarize_if_due(
                    llm=self.llm,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    conversation_history=conversation_history,
                    display_name=display_name,
                    turn_count=turn_count,
                )
            )
        if conversation_id and self.embeddings and prior_search is not None:
            tasks.append(
                SearchEngagementService(
                    session=session, embeddings=self.embeddings
                ).maybe_capture(
                    llm=self.llm,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    prior_search=prior_search,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        # results[0] is the insight list; subsequent entries are persona /
        # events / (optional) slang / (optional) summary / (optional) search.
        insights_result = results[0] if results else []
        events_result = results[2] if len(results) > 2 else []
        persona_result = results[1] if len(results) > 1 else []
        summary_written = False
        slang_calibrated = False
        # Walk the optional tail and identify which kind of result each is
        # so callers get accurate counts even when ordering shifts.
        idx = 3
        if should_calibrate and idx < len(results):
            slang_calibrated = not isinstance(results[idx], BaseException)
            idx += 1
        if (
            conversation_id
            and ConversationSummaryService.should_summarize(turn_count=turn_count)
            and idx < len(results)
        ):
            summary_written = bool(results[idx]) and not isinstance(
                results[idx], BaseException
            )
        took_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "insights_new": (
                len(insights_result) if isinstance(insights_result, list) else 0
            ),
            "insights_superseded": superseded,
            "events_new": (
                len(events_result) if isinstance(events_result, list) else 0
            ),
            "persona_notes": (
                len(persona_result) if isinstance(persona_result, list) else 0
            ),
            "summary_written": summary_written,
            "slang_calibrated": slang_calibrated,
            "took_ms": took_ms,
        }

    async def _run_post_turn_tasks(
        self,
        *,
        user_id: str,
        user_message: str,
        assistant_response: Optional[str],
        memory_insights: list,
        persona_insights: list,
        conversation_history: list,
        should_calibrate: bool,
        active_mode: str = "friends",
        timezone: str | None = None,
        message_created_at: datetime | None = None,
        conversation_id: str | None = None,
        display_name: str = "el usuario",
        turn_count: int = 0,
        prior_search: SearchContext | None = None,
    ) -> None:
        """Run insight extraction, persona evolution, slang calibration, and
        event extraction in a fresh DB session so they survive the
        request-scoped session being closed when the SSE generator returns.
        """
        session_maker = _get_async_session_maker(self.settings)
        async with session_maker() as session:
            try:
                # Wave B.1 — corrections first, so insight extraction
                # doesn't re-add facts the user just retracted in this turn.
                await self._detect_and_apply_corrections(
                    user_id=user_id,
                    message=user_message,
                    session=session,
                )
                tasks = [
                    self._extract_and_store_insights(
                        user_id=user_id,
                        message=user_message,
                        existing_insights=memory_insights,
                        session=session,
                        assistant_response=assistant_response,
                    ),
                    self._evolve_and_store_persona(
                        user_id=user_id,
                        user_message=user_message,
                        assistant_response=assistant_response or "",
                        prior_persona=persona_insights,
                        session=session,
                        active_mode=active_mode,
                    ),
                    self._extract_and_store_events(
                        user_id=user_id,
                        message=user_message,
                        timezone=timezone,
                        message_created_at=message_created_at,
                        session=session,
                        assistant_response=assistant_response,
                    ),
                ]
                if should_calibrate:
                    tasks.append(
                        self._calibrate_and_store_slang(
                            user_id=user_id,
                            conversation_history=conversation_history,
                            session=session,
                        )
                    )
                if conversation_id and ConversationSummaryService.should_summarize(
                    turn_count=turn_count
                ):
                    tasks.append(
                        ConversationSummaryService(session).summarize_if_due(
                            llm=self.llm,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            conversation_history=conversation_history,
                            display_name=display_name,
                            turn_count=turn_count,
                        )
                    )
                if conversation_id and self.embeddings and prior_search is not None:
                    tasks.append(
                        SearchEngagementService(
                            session=session, embeddings=self.embeddings
                        ).maybe_capture(
                            llm=self.llm,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            user_message=user_message,
                            prior_search=prior_search,
                        )
                    )
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                logger.exception(
                    "Post-turn memory tasks failed; reply already delivered to user"
                )


class _MemoryContext:
    """Container for all memory data gathered before response generation."""

    __slots__ = (
        "memory_insights",
        "persona_insights",
        "formality_level",
        "custom_expressions",
        "upcoming_events",
        "prior_summary",
        "transcript_quotes",
    )

    def __init__(
        self,
        memory_insights: list[str] | None = None,
        persona_insights: list[str] | None = None,
        formality_level: float | None = None,
        custom_expressions: list[str] | None = None,
        upcoming_events: list | None = None,
        prior_summary: str | None = None,
        transcript_quotes: list[str] | None = None,
    ) -> None:
        self.memory_insights = memory_insights
        self.persona_insights = persona_insights
        self.formality_level = formality_level
        self.custom_expressions = custom_expressions
        self.upcoming_events = upcoming_events or []
        self.prior_summary = prior_summary
        self.transcript_quotes = transcript_quotes or []


async def _gather_memory(
    service: "ChatService",
    user_id: str,
    message: str,
    session: Optional[AsyncSession],
    active_mode: str = "friends",
    conversation_id: str | None = None,
) -> _MemoryContext:
    """Fetch insights, persona notes, language style, events, and prior summary.

    Five concurrent retrievals; each degrades to a None/empty default on
    failure so a single subsystem outage cannot break chat generation.

    Args:
        service: The ChatService instance.
        user_id: The user's unique identifier.
        message: The current message used for semantic ranking.
        session: Optional database session.
        active_mode: Current avatar mode; passed through to persona retrieval
            so notes from other modes don't leak into this turn's context.
        conversation_id: Rails Conversation id; used to fetch the latest
            non-superseded summary for Phase 13.

    Returns:
        A _MemoryContext with all gathered data.
    """
    results = await asyncio.gather(
        service._get_memory_insights(user_id=user_id, message=message, session=session),
        service._get_persona_insights(
            user_id=user_id, message=message, session=session, active_mode=active_mode
        ),
        service._get_language_style(user_id=user_id, session=session),
        service._get_upcoming_events(user_id=user_id, session=session),
        service._get_prior_summary(conversation_id=conversation_id, session=session),
        service._get_relevant_transcript_quotes(
            user_id=user_id, message=message, session=session
        ),
        return_exceptions=True,
    )
    memory_insights = results[0] if not isinstance(results[0], BaseException) else None
    persona_insights = results[1] if not isinstance(results[1], BaseException) else None

    formality_level = None
    custom_expressions = None
    if not isinstance(results[2], BaseException):
        formality_level, custom_expressions = results[2]

    upcoming_events = results[3] if not isinstance(results[3], BaseException) else []
    prior_summary = results[4] if not isinstance(results[4], BaseException) else None
    transcript_quotes = results[5] if not isinstance(results[5], BaseException) else []

    return _MemoryContext(
        memory_insights=memory_insights,
        persona_insights=persona_insights,
        formality_level=formality_level,
        custom_expressions=custom_expressions,
        upcoming_events=upcoming_events,
        prior_summary=prior_summary,
        transcript_quotes=transcript_quotes,
    )
