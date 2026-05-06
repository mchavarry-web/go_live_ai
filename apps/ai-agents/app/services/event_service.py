"""Service layer for user-event lookups and admin operations.

Mirrors ``MemoryService`` in shape: a thin orchestration layer above
``EventRepository`` that converts ORM rows into Pydantic schemas and
hides the session detail from the route handler.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import UserEvent
from app.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventService:
    """User-events admin/inspection service.

    The avatar's chat-time pipeline talks to ``EventRepository`` directly
    via ``ChatService._get_upcoming_events``; this service is for the
    ``/internal/events/*`` admin surface (debug, GDPR, hallucination kill).

    Args:
        session: Async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = EventRepository(session)

    async def list_upcoming(
        self,
        user_id: str,
        *,
        horizon_days: int = 14,
        limit: int = 50,
    ) -> list[UserEvent]:
        """Return active events occurring within the next ``horizon_days``."""
        rows = await self._repo.list_upcoming(
            user_id,
            now_utc=datetime.now(UTC),
            horizon_days=horizon_days,
            limit=limit,
        )
        return [UserEvent.model_validate(r) for r in rows]

    async def list_all(
        self,
        user_id: str,
        *,
        limit: int = 200,
    ) -> list[UserEvent]:
        """Return every event (any status, past or future) for debug."""
        rows = await self._repo.find_by_user_id(user_id, limit=limit)
        return [UserEvent.model_validate(r) for r in rows]

    async def update_status(
        self,
        user_id: str,
        event_id: str,
        status: str,
    ) -> UserEvent | None:
        """Flip the status of a single event for a specific user."""
        row = await self._repo.mark_status(event_id, user_id, status)
        return UserEvent.model_validate(row) if row else None

    async def delete_for_user(self, user_id: str) -> int:
        """Hard-delete all events for a user (called by GDPR memory wipe)."""
        return await self._repo.delete_by_user_id(user_id)
