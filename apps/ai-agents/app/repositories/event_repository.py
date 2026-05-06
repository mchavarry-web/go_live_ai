"""Repository for user-event database operations.

Handles CRUD for ``UserEventModel`` plus the time-window queries that
drive the avatar's "upcoming commitments" prompt section. Events are
filtered by absolute datetime, never by vector similarity.
"""

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserEventModel
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EventRepository(BaseRepository[UserEventModel]):
    """Repository for ``UserEventModel`` CRUD and time-window queries.

    Surfaces upcoming events for prompt injection and supports the
    cancel/archive lifecycle without a cron sweep (callers archive
    opportunistically on read).

    Attributes:
        model: The ``UserEventModel`` SQLAlchemy class.
    """

    model = UserEventModel

    async def find_by_user_id(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserEventModel]:
        """Find all events for a user, newest first.

        Returns every status — used for the admin "/all" inspection
        endpoint, not the prompt-time retrieval.

        Args:
            user_id: The user's unique identifier.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of ``UserEventModel`` instances.
        """
        stmt = (
            select(UserEventModel)
            .where(UserEventModel.user_id == user_id)
            .order_by(UserEventModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_upcoming(
        self,
        user_id: str,
        *,
        now_utc: datetime,
        horizon_days: int = 14,
        limit: int = 20,
    ) -> list[UserEventModel]:
        """List active events occurring within the next ``horizon_days``.

        This is the hot path — called from ``ChatService._gather_memory``
        on every chat turn. The composite ``ix_user_events_user_occurs``
        index covers the WHERE clause.

        Args:
            user_id: The user's unique identifier.
            now_utc: Current UTC timestamp; events older than this are excluded.
            horizon_days: Window length in days (default 14).
            limit: Maximum events to return.

        Returns:
            Active events in ``[now_utc, now_utc + horizon_days]``, soonest first.
        """
        end_utc = now_utc + timedelta(days=horizon_days)
        stmt = (
            select(UserEventModel)
            .where(
                UserEventModel.user_id == user_id,
                UserEventModel.status == "active",
                UserEventModel.occurs_at >= now_utc,
                UserEventModel.occurs_at <= end_utc,
            )
            .order_by(UserEventModel.occurs_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_window(
        self,
        user_id: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[UserEventModel]:
        """List active events within an explicit ``[start_utc, end_utc]`` window.

        Used by the proactive smart-reminder skill and admin range queries.

        Args:
            user_id: The user's unique identifier.
            start_utc: Window start (inclusive).
            end_utc: Window end (inclusive).

        Returns:
            Active events in the window, soonest first.
        """
        stmt = (
            select(UserEventModel)
            .where(
                UserEventModel.user_id == user_id,
                UserEventModel.status == "active",
                UserEventModel.occurs_at >= start_utc,
                UserEventModel.occurs_at <= end_utc,
            )
            .order_by(UserEventModel.occurs_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_event(
        self,
        *,
        user_id: str,
        title: str,
        occurs_at: datetime,
        occurs_at_has_time: bool,
        raw_text: str,
        source: str,
        source_message_id: str | None,
        confidence: float,
        timezone: str | None,
    ) -> UserEventModel:
        """Persist a new event row.

        Named ``create_event`` rather than ``create`` to avoid shadowing
        ``BaseRepository.create`` (which takes a constructed entity).

        Args:
            user_id: The user's unique identifier.
            title: Short label.
            occurs_at: Absolute UTC timestamp.
            occurs_at_has_time: False when the user gave only a date.
            raw_text: Verbatim message fragment.
            source: Origin string.
            source_message_id: Optional Rails Message id.
            confidence: Extraction confidence (0.0-1.0).
            timezone: IANA tz used to resolve the timestamp.

        Returns:
            The persisted ``UserEventModel``.
        """
        event = UserEventModel(
            id=str(uuid4()),
            user_id=user_id,
            title=title,
            occurs_at=occurs_at,
            occurs_at_has_time=occurs_at_has_time,
            raw_text=raw_text,
            source=source,
            source_message_id=source_message_id,
            confidence=confidence,
            status="active",
            timezone=timezone,
        )
        self._session.add(event)
        await self._session.commit()
        await self._session.refresh(event)

        logger.info(
            "Created event: id=%s, user_id=%s, occurs_at=%s, title=%r",
            event.id,
            user_id,
            occurs_at.isoformat(),
            title,
        )
        return event

    async def find_duplicate(
        self,
        user_id: str,
        *,
        title: str,
        occurs_at: datetime,
        window_minutes: int = 60,
    ) -> UserEventModel | None:
        """Find an active event with the same title within a small time window.

        Prevents double-inserts when the user mentions the same appointment
        in two consecutive turns. Title comparison is case-insensitive on
        the first 50 chars; window defaults to ±60 minutes.

        Args:
            user_id: The user's unique identifier.
            title: Title to match.
            occurs_at: Target timestamp.
            window_minutes: Half-width of the time window.

        Returns:
            A matching event, or None.
        """
        delta = timedelta(minutes=window_minutes)
        title_prefix = title.strip().lower()[:50]
        stmt = (
            select(UserEventModel)
            .where(
                UserEventModel.user_id == user_id,
                UserEventModel.status == "active",
                UserEventModel.occurs_at >= occurs_at - delta,
                UserEventModel.occurs_at <= occurs_at + delta,
            )
        )
        result = await self._session.execute(stmt)
        for row in result.scalars().all():
            if row.title.strip().lower()[:50] == title_prefix:
                return row
        return None

    async def mark_status(
        self,
        event_id: str,
        user_id: str,
        status: str,
    ) -> UserEventModel | None:
        """Update the status of a single event for a specific user.

        Used by the admin endpoint to cancel hallucinated events and by
        ``archive_past`` for individual rows. Bulk archive uses the
        dedicated method.

        Args:
            event_id: The event's unique identifier.
            user_id: The user's unique identifier (ownership guard).
            status: New status — one of "active", "cancelled", "archived".

        Returns:
            The updated event, or None if not found.
        """
        if status not in ("active", "cancelled", "archived"):
            raise ValueError(f"Invalid event status: {status!r}")

        stmt = (
            select(UserEventModel)
            .where(
                UserEventModel.id == event_id,
                UserEventModel.user_id == user_id,
            )
        )
        result = await self._session.execute(stmt)
        event = result.scalar_one_or_none()
        if event is None:
            return None

        event.status = status
        await self._session.commit()
        await self._session.refresh(event)

        logger.info(
            "Updated event status: id=%s, user_id=%s, status=%s",
            event_id,
            user_id,
            status,
        )
        return event

    async def archive_past(
        self,
        user_id: str,
        *,
        before: datetime,
    ) -> int:
        """Bulk-flip active events that ended before ``before`` to ``archived``.

        Called opportunistically from ``ChatService._get_upcoming_events``
        for the current user only — keeps the read window clean without
        running a cron sweep.

        Args:
            user_id: The user's unique identifier.
            before: Threshold UTC timestamp; events with ``occurs_at < before``
                are archived.

        Returns:
            Number of rows updated.
        """
        stmt = (
            update(UserEventModel)
            .where(
                and_(
                    UserEventModel.user_id == user_id,
                    UserEventModel.status == "active",
                    UserEventModel.occurs_at < before,
                )
            )
            .values(status="archived")
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        if count:
            logger.info(
                "Archived %d past events for user_id=%s (before=%s)",
                count,
                user_id,
                before.isoformat(),
            )
        return count

    async def delete_by_user_id(self, user_id: str) -> int:
        """Delete all events for a user (GDPR compliance).

        Symmetric with ``InsightRepository.delete_by_user_id`` — the
        ``/internal/memory/{user_id}`` DELETE handler should call both.

        Args:
            user_id: The user's unique identifier.

        Returns:
            Number of deleted events.
        """
        stmt = delete(UserEventModel).where(UserEventModel.user_id == user_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = result.rowcount or 0
        logger.info(
            "Deleted %d events for user_id=%s (GDPR)",
            count,
            user_id,
        )
        return count
