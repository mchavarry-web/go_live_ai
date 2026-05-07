"""Repository for conversation-summary database operations.

Reads the latest non-superseded summary for a conversation, supersedes
older summaries when a new one lands, and bulk-deletes for GDPR.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ConversationSummaryModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConversationSummaryRepository(BaseRepository[ConversationSummaryModel]):
    """Repository for ``ConversationSummaryModel`` CRUD."""

    model = ConversationSummaryModel

    async def find_by_user_id(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[ConversationSummaryModel]:
        stmt = (
            select(ConversationSummaryModel)
            .where(ConversationSummaryModel.user_id == user_id)
            .order_by(ConversationSummaryModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_conversation(
        self,
        conversation_id: str,
    ) -> ConversationSummaryModel | None:
        """Return the latest non-superseded summary for a conversation."""
        stmt = (
            select(ConversationSummaryModel)
            .where(
                ConversationSummaryModel.conversation_id == conversation_id,
                ConversationSummaryModel.superseded_at.is_(None),
            )
            .order_by(ConversationSummaryModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def supersede_then_create(
        self,
        *,
        user_id: str,
        conversation_id: str,
        summary: str,
        message_count: int,
        summary_token_count: int,
        range_start_message_id: str | None,
        range_end_message_id: str | None,
    ) -> ConversationSummaryModel:
        """Mark prior summaries superseded and persist a fresh one.

        Single-transaction-ish (commit at the end) so callers don't see a
        window where two non-superseded rows exist for the same
        conversation. Race-tolerant: a duplicate summary just produces a
        second row that itself supersedes the first on next write.
        """
        now = datetime.now(UTC)
        await self._session.execute(
            update(ConversationSummaryModel)
            .where(
                ConversationSummaryModel.conversation_id == conversation_id,
                ConversationSummaryModel.superseded_at.is_(None),
            )
            .values(superseded_at=now)
        )
        row = ConversationSummaryModel(
            id=str(uuid4()),
            user_id=user_id,
            conversation_id=conversation_id,
            summary=summary,
            message_count=message_count,
            summary_token_count=summary_token_count,
            range_start_message_id=range_start_message_id,
            range_end_message_id=range_end_message_id,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        logger.info(
            "Persisted summary id=%s conv=%s message_count=%d tokens=%d",
            row.id,
            conversation_id,
            message_count,
            summary_token_count,
        )
        return row

    async def delete_by_user_id(self, user_id: str) -> int:
        stmt = delete(ConversationSummaryModel).where(
            ConversationSummaryModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        logger.info("Deleted %d conversation summaries for user_id=%s (GDPR)", count, user_id)
        return count
