"""Repository for ``user_style_profiles`` (Wave B.3, 2026-05-06).

One row per user; updates are upserts — the calibrator overwrites the
core fields each pass, leaving reserved-for-future fields untouched.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserStyleProfileModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserStyleProfileRepository(BaseRepository[UserStyleProfileModel]):
    """Repository for ``UserStyleProfileModel``."""

    model = UserStyleProfileModel

    async def find_by_user_id(
        self, user_id: str, limit: int = 1
    ) -> list[UserStyleProfileModel]:
        stmt = (
            select(UserStyleProfileModel)
            .where(UserStyleProfileModel.user_id == user_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user(self, user_id: str) -> UserStyleProfileModel | None:
        rows = await self.find_by_user_id(user_id, limit=1)
        return rows[0] if rows else None

    async def upsert_core(
        self,
        *,
        user_id: str,
        formality_level: float | None,
        custom_expressions: list[str] | None,
        emoji_frequency: str | None,
    ) -> UserStyleProfileModel:
        """Create or update the calibrator-driven fields.

        Reserved fields (sentence_length_avg, common_greetings, etc.)
        are left untouched on update so a future style-extractor chain
        can populate them independently.
        """
        existing = await self.get_for_user(user_id)
        if existing is None:
            row = UserStyleProfileModel(
                id=str(uuid4()),
                user_id=user_id,
                formality_level=formality_level,
                custom_expressions=custom_expressions or [],
                emoji_frequency=emoji_frequency,
                sample_count=1,
            )
            self._session.add(row)
            await self._session.commit()
            await self._session.refresh(row)
            return row
        existing.formality_level = formality_level
        existing.custom_expressions = custom_expressions or []
        existing.emoji_frequency = emoji_frequency
        existing.sample_count = (existing.sample_count or 0) + 1
        existing.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def delete_by_user_id(self, user_id: str) -> int:
        stmt = delete(UserStyleProfileModel).where(
            UserStyleProfileModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        if count:
            logger.info(
                "Deleted %d style profile rows for user_id=%s",
                count,
                user_id,
            )
        return count
