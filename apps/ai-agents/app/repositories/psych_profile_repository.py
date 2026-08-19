"""Repository for ``psych_profiles`` (DEV-98, 2026-08-15).

One current row per (user_id, provider); writes are upserts — a re-run
of a provider overwrites its previous traits/raw payload in place.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import PsychProfileModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PsychProfileRepository(BaseRepository[PsychProfileModel]):
    """Repository for ``PsychProfileModel``."""

    model = PsychProfileModel

    async def list_for_user(self, user_id: str) -> list[PsychProfileModel]:
        """Return every stored profile row for a user (max one per provider)."""
        stmt = (
            select(PsychProfileModel)
            .where(PsychProfileModel.user_id == user_id)
            .order_by(PsychProfileModel.provider)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user_provider(
        self, user_id: str, provider: str
    ) -> PsychProfileModel | None:
        """Return the current row for (user_id, provider), or None."""
        stmt = (
            select(PsychProfileModel)
            .where(
                PsychProfileModel.user_id == user_id,
                PsychProfileModel.provider == provider,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self,
        *,
        user_id: str,
        provider: str,
        traits: dict,
        raw: dict | None = None,
        source_summary: str | None = None,
    ) -> PsychProfileModel:
        """Create or overwrite the (user_id, provider) row."""
        existing = await self.get_for_user_provider(user_id, provider)
        if existing is None:
            row = PsychProfileModel(
                id=str(uuid4()),
                user_id=user_id,
                provider=provider,
                traits=traits,
                raw=raw,
                source_summary=source_summary,
            )
            self._session.add(row)
            await self._session.commit()
            await self._session.refresh(row)
            return row
        existing.traits = traits
        existing.raw = raw
        existing.source_summary = source_summary
        existing.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def delete_by_user_id(self, user_id: str) -> int:
        """Delete every profile row for a user (GDPR wipe path)."""
        stmt = delete(PsychProfileModel).where(
            PsychProfileModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        if count:
            logger.info(
                "Deleted %d psych profile rows for user_id=%s",
                count,
                user_id,
            )
        return count
