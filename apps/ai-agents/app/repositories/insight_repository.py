"""Repository for insight database operations.

Handles CRUD operations for the InsightModel, including vector
similarity search via pgvector and bulk deletion for GDPR compliance.
"""

import logging
from uuid import uuid4

from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import InsightModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class InsightRepository(BaseRepository[InsightModel]):
    """Repository for InsightModel CRUD and vector similarity search.

    Extends BaseRepository with pgvector-powered semantic search
    and bulk operations for user data management.

    Attributes:
        model: The InsightModel SQLAlchemy class.
    """

    model = InsightModel

    async def find_by_user_id(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InsightModel]:
        """Find all insights for a user, ordered by creation date.

        Args:
            user_id: The user's unique identifier.
            limit: Maximum number of results to return.
            offset: Number of results to skip (pagination).

        Returns:
            List of InsightModel instances for the specified user.
        """
        stmt = (
            select(InsightModel)
            .where(InsightModel.user_id == user_id)
            .order_by(InsightModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user_id(self, user_id: str) -> int:
        """Count total insights for a user.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Total number of insights for the user.
        """
        stmt = (
            select(func.count())
            .select_from(InsightModel)
            .where(InsightModel.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        categories: list[str] | None = None,
        sources: list[str] | None = None,
        max_distance: float | None = None,
        include_superseded: bool = False,
    ) -> list[InsightModel]:
        """Search for semantically similar insights using pgvector cosine distance.

        Args:
            user_id: The user's unique identifier.
            query_embedding: The query vector (1536 dimensions).
            top_k: Number of top results to return.
            categories: Optional list of categories to filter by.
            sources: Optional list of exact source strings to filter by.
                Applied at the SQL level so the LIMIT only sees matching
                rows (otherwise rival modes can crowd out the active one).
            max_distance: Optional cosine-distance ceiling (lower = closer).
                Wave A.2 (2026-05-06). When set, rows beyond this distance
                are excluded at the SQL level so the prompt never sees
                weakly-related insights. Recommended: 0.40 for user facts,
                0.45 for persona, 0.15 for dedupe lookups. None preserves
                the original top-k-only behaviour for admin/debug callers.

        Returns:
            List of InsightModel instances ordered by cosine similarity.
        """
        # Build base filter conditions
        conditions = [
            InsightModel.user_id == user_id,
            InsightModel.embedding.isnot(None),
        ]
        if not include_superseded:
            # Wave B.1 — don't surface superseded/corrected rows. Audit
            # endpoints that need them pass include_superseded=True.
            conditions.append(InsightModel.status == "active")
        if categories:
            conditions.append(InsightModel.category.in_(categories))
        if sources:
            conditions.append(InsightModel.source.in_(sources))

        distance_expr = InsightModel.embedding.cosine_distance(query_embedding)
        if max_distance is not None:
            conditions.append(distance_expr <= max_distance)

        stmt = (
            select(InsightModel)
            .where(*conditions)
            .order_by(distance_expr)
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_with_embedding(
        self,
        user_id: str,
        category: str,
        content: str,
        confidence: float,
        source: str,
        embedding: list[float] | None = None,
    ) -> InsightModel:
        """Create a new insight with an optional vector embedding.

        Args:
            user_id: The user's unique identifier.
            category: Insight category (e.g., "preference", "goal").
            content: The insight text content.
            confidence: Extraction confidence score (0.0-1.0).
            source: Origin of the insight (e.g., "conversation").
            embedding: Optional vector embedding (1536 dimensions).

        Returns:
            The persisted InsightModel instance.
        """
        insight = InsightModel(
            id=str(uuid4()),
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            embedding=embedding,
        )
        self._session.add(insight)
        await self._session.commit()
        await self._session.refresh(insight)

        logger.info(
            "Created insight: id=%s, user_id=%s, category=%s",
            insight.id,
            user_id,
            category,
        )
        return insight

    async def delete_by_user_id(self, user_id: str) -> int:
        """Delete all insights for a user (GDPR compliance).

        Args:
            user_id: The user's unique identifier.

        Returns:
            Number of deleted insights.
        """
        stmt = (
            delete(InsightModel)
            .where(InsightModel.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()

        count = result.rowcount
        logger.info(
            "Deleted %d insights for user_id=%s (GDPR)",
            count,
            user_id,
        )
        return count

    async def find_by_id_and_user(
        self,
        insight_id: str,
        user_id: str,
    ) -> InsightModel | None:
        """Find a single insight by ID ensuring it belongs to the user.

        Args:
            insight_id: The insight's unique identifier.
            user_id: The user's unique identifier.

        Returns:
            The InsightModel if found and owned by user, None otherwise.
        """
        stmt = (
            select(InsightModel)
            .where(
                InsightModel.id == insight_id,
                InsightModel.user_id == user_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_source(
        self,
        user_id: str,
        source: str,
        prefix: bool = False,
    ) -> int:
        """Delete insights for a user that match the given source.

        Args:
            user_id: The user's unique identifier.
            source: Exact source string (e.g. "audio:<session_id>"), or a
                prefix (e.g. "audio") when ``prefix`` is True.
            prefix: If True, match any source starting with ``source + ":"``
                or equal to ``source``. Useful for "delete all audio insights".

        Returns:
            Number of deleted insights.
        """
        if prefix:
            stmt = (
                delete(InsightModel)
                .where(
                    InsightModel.user_id == user_id,
                    (InsightModel.source == source) | InsightModel.source.like(f"{source}:%"),
                )
            )
        else:
            stmt = (
                delete(InsightModel)
                .where(
                    InsightModel.user_id == user_id,
                    InsightModel.source == source,
                )
            )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount
        logger.info(
            "Deleted %d insights for user_id=%s by source=%s prefix=%s",
            count,
            user_id,
            source,
            prefix,
        )
        return count

    async def delete_by_id_and_user(
        self,
        insight_id: str,
        user_id: str,
    ) -> bool:
        """Delete a single insight by ID for a specific user.

        Args:
            insight_id: The insight's unique identifier.
            user_id: The user's unique identifier.

        Returns:
            True if the insight was deleted, False if not found.
        """
        stmt = (
            delete(InsightModel)
            .where(
                InsightModel.id == insight_id,
                InsightModel.user_id == user_id,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(
                "Deleted insight id=%s for user_id=%s",
                insight_id,
                user_id,
            )
        return deleted

    async def update_content(
        self,
        insight_id: str,
        user_id: str,
        content: str,
        embedding: list[float] | None = None,
    ) -> InsightModel | None:
        """Update the content (and optionally embedding) of a single insight.

        Args:
            insight_id: The insight's unique identifier.
            user_id: The user's unique identifier.
            content: New content text.
            embedding: New embedding vector (regenerated for the content).

        Returns:
            The updated InsightModel, or None if not found.
        """
        insight = await self.find_by_id_and_user(insight_id, user_id)
        if not insight:
            return None

        insight.content = content
        if embedding is not None:
            insight.embedding = embedding

        await self._session.commit()
        await self._session.refresh(insight)

        logger.info(
            "Updated insight id=%s for user_id=%s",
            insight_id,
            user_id,
        )
        return insight

    async def count_by_category(
        self,
        user_id: str,
    ) -> dict[str, int]:
        """Count insights grouped by category for a user.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Dict mapping category name to count.
        """
        stmt = (
            select(InsightModel.category, func.count())
            .where(InsightModel.user_id == user_id)
            .group_by(InsightModel.category)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def supersede_ids(
        self,
        user_id: str,
        insight_ids: list[str],
        *,
        superseded_by_id: str | None = None,
        status: str = "superseded",
    ) -> int:
        """Mark a batch of rows as superseded/corrected.

        Wave B.1 (2026-05-06). Used by ``CorrectionDetectorChain``'s
        downstream when the user retracts or updates a fact. Rows are
        not deleted — kept for audit. Retrieval filters them out via
        ``status='active'``.

        Args:
            user_id: The user's unique identifier (ownership guard).
            insight_ids: Rows to flip.
            superseded_by_id: Optional id of the row that replaced these.
            status: Target status; either 'superseded' or 'corrected'.

        Returns:
            Number of rows updated.
        """
        if status not in ("superseded", "corrected"):
            raise ValueError(f"Invalid superseded status: {status!r}")
        if not insight_ids:
            return 0
        stmt = (
            update(InsightModel)
            .where(
                InsightModel.user_id == user_id,
                InsightModel.id.in_(insight_ids),
                InsightModel.status == "active",
            )
            .values(
                status=status,
                superseded_at=datetime.now(UTC),
                superseded_by_id=superseded_by_id,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        if count:
            logger.info(
                "Superseded %d insights for user_id=%s status=%s",
                count,
                user_id,
                status,
            )
        return count

    async def count_by_source(
        self,
        user_id: str,
    ) -> dict[str, int]:
        """Count insights grouped by source for a user.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Dict mapping source name to count.
        """
        stmt = (
            select(InsightModel.source, func.count())
            .where(InsightModel.user_id == user_id)
            .group_by(InsightModel.source)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
