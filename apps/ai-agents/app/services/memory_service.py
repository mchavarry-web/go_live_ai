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
from app.repositories.insight_repository import InsightRepository

logger = logging.getLogger(__name__)


# ── Knowledge Level Calculation ──────────────────────────────────────────

def calculate_knowledge_level(total_insights: int) -> int:
    """Calculate the avatar's knowledge level based on total insights.

    Uses a tiered system:
        0-2 insights  -> Level 1
        3-5 insights  -> Level 2
        6-10 insights -> Level 3
        11-20 insights -> Level 4
        21+ insights  -> Level 5

    Args:
        total_insights: Total number of stored insights for the user.

    Returns:
        Knowledge level from 1 to 5.
    """
    if total_insights <= 2:
        return 1
    elif total_insights <= 5:
        return 2
    elif total_insights <= 10:
        return 3
    elif total_insights <= 20:
        return 4
    else:
        return 5


# ── Memory Service ───────────────────────────────────────────────────────


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
        knowledge_level = calculate_knowledge_level(total)

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
            knowledge_level=knowledge_level,
            insights=insight_schemas,
        )

    async def get_relevant_insights(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        categories: list[str] | None = None,
        sources: list[str] | None = None,
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
    ) -> list[InsightModel]:
        """Store extracted insights with their vector embeddings.

        Generates embeddings for each insight and stores them in the database.

        Args:
            user_id: The user's unique identifier.
            insights: List of dicts with keys: category, content, confidence.
            source: Origin of the insights (default: "conversation").

        Returns:
            List of created InsightModel instances.
        """
        if not insights:
            return []

        created = []
        for insight_data in insights:
            content = insight_data["content"]

            # Generate embedding for the insight
            try:
                embedding = await self.embeddings.aembed_query(content)
            except Exception:
                logger.warning(
                    "Failed to generate embedding for insight, storing without vector"
                )
                embedding = None

            insight = await self.repository.create_with_embedding(
                user_id=user_id,
                category=insight_data["category"],
                content=content,
                confidence=insight_data["confidence"],
                source=source,
                embedding=embedding,
            )
            created.append(insight)

        logger.info(
            "Stored %d insights for user_id=%s",
            len(created),
            user_id,
        )
        return created

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

        Removes all insights and their embeddings.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Number of deleted insights.
        """
        count = await self.repository.delete_by_user_id(user_id)
        logger.info(
            "GDPR: Deleted %d insights for user_id=%s",
            count,
            user_id,
        )
        return count

    async def get_knowledge_level(self, user_id: str) -> int:
        """Get the current knowledge level for a user.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Knowledge level from 1 to 5.
        """
        total = await self.repository.count_by_user_id(user_id)
        return calculate_knowledge_level(total)

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
