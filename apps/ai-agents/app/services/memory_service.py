"""Memory service for managing user memory operations.

Provides an interface to the insight repository and embedding system
for storing, retrieving, and searching user insights. Handles knowledge
level calculation and GDPR-compliant data deletion.
"""

import logging
from typing import Optional

from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import InsightModel
from app.models.schemas import Insight, MemoryResponse
from app.repositories.audio_transcript_repository import AudioTranscriptRepository
from app.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from app.repositories.event_repository import EventRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.psych_profile_repository import PsychProfileRepository
from app.repositories.user_style_profile_repository import UserStyleProfileRepository

logger = logging.getLogger(__name__)


# ── Memory Service ───────────────────────────────────────────────────────
#
# NOTE: a per-insight-count tiered "knowledge_level" used to live here.
# It was removed when Rails' Avatar.knowledge_level (log-scaled, multi-signal,
# 1-10) became the canonical formula. FastAPI now treats knowledge_level as
# read-only input passed through ChatGenerateRequest.user_profile, never
# recomputes it. See `apps/backend/app/models/avatar.rb` for the formula.

# Wave A.3 (2026-05-06) — pre-insert dedupe constants. A near-duplicate is
# anything within DEDUPE_DISTANCE_THRESHOLD cosine distance of an existing
# same-user, same-category insight. We replace the existing row only when
# the new confidence is at least DEDUPE_CONFIDENCE_UPLIFT higher; otherwise
# we silently skip the insert and reuse the existing row.
_DEDUPE_DISTANCE_THRESHOLD = 0.15
_DEDUPE_CONFIDENCE_UPLIFT = 0.10


class MemoryService:
    """Service for managing user memory through insights and embeddings.

    Coordinates InsightRepository and LangChain Embeddings to provide
    semantic memory capabilities for the avatar.

    Attributes:
        repository: InsightRepository for database operations.
        embeddings: LangChain Embeddings model for vector generation.
    """

    def __init__(
        self,
        session: AsyncSession,
        embeddings: Embeddings,
    ) -> None:
        """Initialize the memory service.

        Args:
            session: Async SQLAlchemy database session.
            embeddings: LangChain Embeddings instance.
        """
        self._session = session
        self.repository = InsightRepository(session)
        self.embeddings = embeddings

    async def get_user_memory(self, user_id: str) -> MemoryResponse:
        """Get the memory summary for a user.

        Retrieves all insights and calculates the current knowledge level.

        Args:
            user_id: The user's unique identifier.

        Returns:
            MemoryResponse with user insights and knowledge level.
        """
        insights = await self.repository.find_by_user_id(user_id)
        total = await self.repository.count_by_user_id(user_id)

        insight_schemas = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in insights
        ]

        return MemoryResponse(
            user_id=user_id,
            total_insights=total,
            insights=insight_schemas,
        )

    async def get_relevant_insights(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        categories: list[str] | None = None,
        sources: list[str] | None = None,
        max_distance: float | None = None,
    ) -> list[InsightModel]:
        """Search for insights relevant to a query using semantic similarity.

        Generates an embedding for the query and searches for similar
        insights in the vector store.

        Args:
            user_id: The user's unique identifier.
            query: The search query (e.g., the user's message).
            top_k: Number of results to return.
            categories: Optional category filter.
            sources: Optional source filter applied at the SQL level so the
                LIMIT only sees matching rows (e.g. mode-scoped persona).
            max_distance: Optional cosine-distance ceiling. Wave A.2
                (2026-05-06). Pass-through to the repository so chat-time
                callers can exclude weakly-related insights from the prompt.

        Returns:
            List of InsightModel instances ordered by relevance.
        """
        try:
            query_embedding = await self.embeddings.aembed_query(query)
            return await self.repository.search_similar(
                user_id=user_id,
                query_embedding=query_embedding,
                top_k=top_k,
                categories=categories,
                sources=sources,
                max_distance=max_distance,
            )
        except Exception:
            logger.exception(
                "Semantic search failed for user_id=%s, falling back to recent insights",
                user_id,
            )
            # Fallback: return most recent insights if vector search fails
            return await self.repository.find_by_user_id(user_id, limit=top_k)

    async def store_insights(
        self,
        user_id: str,
        insights: list[dict],
        source: str = "conversation",
        dedupe: bool = True,
    ) -> list[InsightModel]:
        """Store extracted insights with their vector embeddings.

        Wave A.3 (2026-05-06) added pre-insert dedupe. The default flow is:

        1. Batch-embed all candidates in a single ``aembed_documents`` call
           so the round-trip cost is paid once per turn.
        2. For each candidate, look up same-user/same-category insights
           within ``_DEDUPE_DISTANCE_THRESHOLD`` cosine distance.
        3. On match:
           - If the new confidence is ≥ existing + ``_DEDUPE_CONFIDENCE_UPLIFT``,
             update the existing row's content + confidence + embedding.
           - Otherwise reuse the existing row silently.
        4. On no match, create a new row as before.

        Pass ``dedupe=False`` to bypass — admin / debug paths that want a
        force-insert (or callers passing slang_calibration JSON-blob content
        that doesn't dedupe meaningfully).

        Args:
            user_id: The user's unique identifier.
            insights: List of dicts with keys: category, content, confidence.
            source: Origin of the insights (default: "conversation").
            dedupe: Run the pre-insert dedupe path. Default True.

        Returns:
            List of InsightModel instances — created OR reused. Length matches
            the input length when dedupe is off; when on, near-duplicate
            inputs return the matched existing row instead.
        """
        if not insights:
            return []

        # Step 1 — batch embed. Falling back to per-insight queries on
        # batch failure preserves the original behaviour (storing without
        # a vector) instead of dropping rows.
        contents = [data["content"] for data in insights]
        embeddings: list[list[float] | None]
        try:
            embeddings = list(await self.embeddings.aembed_documents(contents))
        except Exception:
            logger.warning(
                "Batch embedding failed for %d insights — falling back to per-row attempts",
                len(contents),
            )
            embeddings = []
            for content in contents:
                try:
                    embeddings.append(await self.embeddings.aembed_query(content))
                except Exception:
                    embeddings.append(None)

        results: list[InsightModel] = []
        new_rows = 0
        updated_rows = 0
        skipped_rows = 0

        for insight_data, embedding in zip(insights, embeddings):
            content = insight_data["content"]
            category = insight_data["category"]
            confidence = float(insight_data["confidence"])

            existing = None
            if dedupe and embedding is not None:
                existing = await self._find_near_duplicate(
                    user_id=user_id,
                    category=category,
                    embedding=embedding,
                )

            if existing is not None:
                if confidence >= (existing.confidence or 0.0) + _DEDUPE_CONFIDENCE_UPLIFT:
                    updated = await self.repository.update_content(
                        insight_id=existing.id,
                        user_id=user_id,
                        content=content,
                        embedding=embedding,
                    )
                    if updated is not None:
                        updated.confidence = confidence
                        updated.source = source
                        await self._session.commit()
                        await self._session.refresh(updated)
                        results.append(updated)
                        updated_rows += 1
                        continue
                results.append(existing)
                skipped_rows += 1
                continue

            insight = await self.repository.create_with_embedding(
                user_id=user_id,
                category=category,
                content=content,
                confidence=confidence,
                source=source,
                embedding=embedding,
            )
            results.append(insight)
            new_rows += 1

        logger.info(
            "store_insights user_id=%s source=%s: %d new, %d updated, %d deduped",
            user_id,
            source,
            new_rows,
            updated_rows,
            skipped_rows,
        )
        return results

    async def apply_corrections(
        self,
        user_id: str,
        corrections: list,
        *,
        max_distance: float = 0.40,
        per_target: int = 2,
    ) -> int:
        """Mark insights matching ``corrections`` as superseded.

        Wave B.1 (2026-05-06). For each ``CorrectionSignal``, embed its
        ``target_phrase`` and find up to ``per_target`` same-category
        insights within ``max_distance``. Flip them to ``status='superseded'``
        in one bulk update per signal so retrieval stops surfacing the
        retracted facts.

        Args:
            user_id: The user's unique identifier.
            corrections: List of objects with ``target_phrase``,
                ``category_hint`` (optional), and ``confidence``. The
                shape is ``app.chains.correction_detector_chain.CorrectionSignal``
                but kept duck-typed so the service stays decoupled from
                the chain module.
            max_distance: Cosine ceiling for the supersede search. Looser
                than retrieval (0.40 vs 0.40 default for facts) — we
                want to catch reasonable rewordings.
            per_target: Max rows superseded per correction signal.

        Returns:
            Total rows superseded across all signals.
        """
        if not corrections or not self.embeddings:
            return 0
        total = 0
        for sig in corrections:
            target = getattr(sig, "target_phrase", None) or ""
            if not target.strip():
                continue
            try:
                embedding = await self.embeddings.aembed_query(target)
            except Exception:
                logger.warning(
                    "Correction embedding failed user_id=%s target=%r",
                    user_id,
                    target,
                    exc_info=True,
                )
                continue
            categories = None
            hint = getattr(sig, "category_hint", None)
            if hint:
                categories = [hint]
            try:
                matches = await self.repository.search_similar(
                    user_id=user_id,
                    query_embedding=embedding,
                    top_k=per_target,
                    categories=categories,
                    max_distance=max_distance,
                )
            except Exception:
                logger.warning(
                    "Correction search failed user_id=%s target=%r",
                    user_id,
                    target,
                    exc_info=True,
                )
                continue
            ids = [m.id for m in matches]
            if not ids:
                continue
            count = await self.repository.supersede_ids(
                user_id=user_id,
                insight_ids=ids,
                status="superseded",
            )
            total += count
            logger.info(
                "Superseded %d insights for user_id=%s target=%r",
                count,
                user_id,
                target,
            )
        return total

    async def _find_near_duplicate(
        self,
        *,
        user_id: str,
        category: str,
        embedding: list[float],
    ) -> InsightModel | None:
        """Return the closest same-user/same-category insight within the
        dedupe threshold, or None.

        Wave A.3 (2026-05-06). Used by ``store_insights`` to avoid
        accumulating near-identical rows when an insight is repeatedly
        extracted across turns.
        """
        try:
            matches = await self.repository.search_similar(
                user_id=user_id,
                query_embedding=embedding,
                top_k=1,
                categories=[category],
                max_distance=_DEDUPE_DISTANCE_THRESHOLD,
            )
        except Exception:
            logger.warning(
                "Dedupe lookup failed user_id=%s category=%s — proceeding with insert",
                user_id,
                category,
                exc_info=True,
            )
            return None
        return matches[0] if matches else None

    async def delete_insights_by_source(
        self,
        user_id: str,
        source: str,
        prefix: bool = False,
    ) -> int:
        """Delete every insight for a user that matches a source.

        Used by Rails for audio-session wipes:
            • prefix=False, source="audio:<sid>" → one session
            • prefix=True,  source="audio"      → every audio insight

        Args:
            user_id: The user's unique identifier.
            source: Exact match, or prefix to be matched as ``source`` or
                ``source:%`` when ``prefix`` is True.
            prefix: When True, treat ``source`` as a leading namespace.

        Returns:
            Number of deleted insights.
        """
        return await self.repository.delete_by_source(user_id, source, prefix)

    async def delete_user_memory(self, user_id: str) -> int:
        """Delete all memory for a user (GDPR compliance).

        Removes all insights, their embeddings, and any user_events rows.
        Returned count reflects insights only (the historical contract);
        deleted event count is logged separately.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Number of deleted insights.
        """
        count = await self.repository.delete_by_user_id(user_id)
        event_count = -1
        summary_count = -1
        transcript_count = -1
        try:
            event_count = await EventRepository(self._session).delete_by_user_id(user_id)
        except Exception:
            logger.exception(
                "GDPR: event wipe failed for user_id=%s — insights already deleted",
                user_id,
            )
        try:
            summary_count = await ConversationSummaryRepository(
                self._session
            ).delete_by_user_id(user_id)
        except Exception:
            logger.exception(
                "GDPR: conversation-summary wipe failed for user_id=%s",
                user_id,
            )
        try:
            transcript_count = await AudioTranscriptRepository(
                self._session
            ).delete_by_user_id(user_id)
        except Exception:
            logger.exception(
                "GDPR: transcript-chunk wipe failed for user_id=%s",
                user_id,
            )
        style_count = -1
        try:
            style_count = await UserStyleProfileRepository(
                self._session
            ).delete_by_user_id(user_id)
        except Exception:
            logger.exception(
                "GDPR: user_style_profile wipe failed for user_id=%s",
                user_id,
            )
        psych_count = -1
        try:
            psych_count = await PsychProfileRepository(
                self._session
            ).delete_by_user_id(user_id)
        except Exception:
            logger.exception(
                "GDPR: psych_profile wipe failed for user_id=%s",
                user_id,
            )
        logger.info(
            "GDPR: Deleted %d insights, %d events, %d summaries, %d transcript chunks, %d style profiles, %d psych profiles for user_id=%s",
            count,
            event_count,
            summary_count,
            transcript_count,
            style_count,
            psych_count,
            user_id,
        )
        return count

    async def delete_insight(self, user_id: str, insight_id: str) -> bool:
        """Delete a single insight for a user.

        Args:
            user_id: The user's unique identifier.
            insight_id: The insight's unique identifier.

        Returns:
            True if the insight was deleted, False if not found.
        """
        deleted = await self.repository.delete_by_id_and_user(insight_id, user_id)
        if deleted:
            logger.info(
                "Deleted single insight id=%s for user_id=%s",
                insight_id,
                user_id,
            )
        return deleted

    async def update_insight(
        self,
        user_id: str,
        insight_id: str,
        content: str,
    ) -> InsightModel | None:
        """Update the content of a single insight, regenerating its embedding.

        Args:
            user_id: The user's unique identifier.
            insight_id: The insight's unique identifier.
            content: The new content text.

        Returns:
            The updated InsightModel, or None if not found.
        """
        # Generate new embedding for the updated content
        try:
            embedding = await self.embeddings.aembed_query(content)
        except Exception:
            logger.warning(
                "Failed to regenerate embedding for insight %s, updating without vector",
                insight_id,
            )
            embedding = None

        updated = await self.repository.update_content(
            insight_id=insight_id,
            user_id=user_id,
            content=content,
            embedding=embedding,
        )
        if updated:
            logger.info(
                "Updated insight id=%s for user_id=%s",
                insight_id,
                user_id,
            )
        return updated

    async def get_insights_by_category(self, user_id: str) -> dict[str, int]:
        """Get the count of insights grouped by category.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Dict mapping category to count.
        """
        return await self.repository.count_by_category(user_id)

    async def get_insights_by_source(self, user_id: str) -> dict[str, int]:
        """Get the count of insights grouped by source.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Dict mapping source to count.
        """
        return await self.repository.count_by_source(user_id)
