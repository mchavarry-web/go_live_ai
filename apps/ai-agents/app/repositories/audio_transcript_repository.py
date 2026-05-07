"""Repository for embedded audio-transcript chunks (Phase 14).

Separate retrieval pool from ``insights``. Reads via pgvector cosine
similarity; writes are batched so a 5-minute audio chunk producing
60 windows commits in one shot.
"""

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AudioTranscriptChunkModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AudioTranscriptRepository(BaseRepository[AudioTranscriptChunkModel]):
    """Repository for ``AudioTranscriptChunkModel`` CRUD + similarity search."""

    model = AudioTranscriptChunkModel

    async def find_by_user_id(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[AudioTranscriptChunkModel]:
        stmt = (
            select(AudioTranscriptChunkModel)
            .where(AudioTranscriptChunkModel.user_id == user_id)
            .order_by(AudioTranscriptChunkModel.recorded_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(
        self,
        *,
        user_id: str,
        audio_chunk_id: str,
        audio_session_id: str,
        recorded_at: datetime,
        windows: list[str],
        embeddings: list[list[float] | None],
    ) -> int:
        """Persist a chunk's worth of transcript windows in one commit.

        ``windows`` and ``embeddings`` must align by index. Embeddings can
        contain ``None`` slots so the caller is free to skip embedding on
        empty/dud windows; those rows still persist (queryable by
        recorded_at) but won't surface in semantic search.
        """
        if not windows:
            return 0
        if len(windows) != len(embeddings):
            raise ValueError(
                f"windows ({len(windows)}) and embeddings ({len(embeddings)}) length mismatch"
            )

        rows = [
            AudioTranscriptChunkModel(
                id=str(uuid4()),
                user_id=user_id,
                audio_chunk_id=audio_chunk_id,
                audio_session_id=audio_session_id,
                sequence_in_chunk=idx,
                text=text,
                embedding=embedding,
                recorded_at=recorded_at,
            )
            for idx, (text, embedding) in enumerate(zip(windows, embeddings))
        ]
        self._session.add_all(rows)
        await self._session.commit()
        logger.info(
            "Persisted %d transcript chunks user_id=%s audio_chunk=%s",
            len(rows),
            user_id,
            audio_chunk_id,
        )
        return len(rows)

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        *,
        top_k: int = 3,
        max_distance: float = 0.25,
    ) -> list[AudioTranscriptChunkModel]:
        """Return the top-k transcript windows by cosine distance.

        ``max_distance`` is the cosine-distance ceiling (lower = closer).
        0.25 maps to roughly cosine_similarity >= 0.75 — strict enough
        that we don't surface tangentially-related quotes.
        """
        stmt = (
            select(AudioTranscriptChunkModel)
            .where(
                AudioTranscriptChunkModel.user_id == user_id,
                AudioTranscriptChunkModel.embedding.isnot(None),
            )
            .order_by(AudioTranscriptChunkModel.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        # Filter rows whose distance exceeds the threshold (post-fetch
        # because computing distance twice is fine at top_k=3).
        kept: list[AudioTranscriptChunkModel] = []
        for row in rows:
            try:
                # Recompute distance for the threshold check.
                if row.embedding is None:
                    continue
                # Manual cosine distance: 1 - (a·b / (|a||b|)).
                a = row.embedding
                b = query_embedding
                dot = sum(x * y for x, y in zip(a, b))
                na = sum(x * x for x in a) ** 0.5
                nb = sum(y * y for y in b) ** 0.5
                if na == 0 or nb == 0:
                    continue
                distance = 1.0 - dot / (na * nb)
                if distance <= max_distance:
                    kept.append(row)
            except Exception:
                continue
        return kept

    async def delete_by_user_id(self, user_id: str) -> int:
        stmt = delete(AudioTranscriptChunkModel).where(
            AudioTranscriptChunkModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        logger.info("Deleted %d transcript chunks for user_id=%s (GDPR)", count, user_id)
        return count

    async def delete_by_session(self, user_id: str, audio_session_id: str) -> int:
        stmt = delete(AudioTranscriptChunkModel).where(
            AudioTranscriptChunkModel.user_id == user_id,
            AudioTranscriptChunkModel.audio_session_id == audio_session_id,
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        logger.info(
            "Deleted %d transcript chunks user_id=%s session=%s",
            count,
            user_id,
            audio_session_id,
        )
        return count
