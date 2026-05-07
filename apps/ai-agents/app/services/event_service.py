"""Service layer for user-event lookups, admin operations, and shared
extract-and-store orchestration.

Mirrors ``MemoryService`` in shape: a thin orchestration layer above
``EventRepository`` that converts ORM rows into Pydantic schemas, hides
session detail from route handlers, and exposes a single
``extract_and_store_from_text`` entrypoint that chat / audio / social
ingest all call. Centralising that pipeline keeps the dedupe loop and
confidence floors consistent across input channels.
"""

import logging
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.event_extraction_chain import EventExtractionChain
from app.models.schemas import UserEvent
from app.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)

_DEFAULT_TIMEZONE = "America/Lima"


class EventService:
    """User-events service: extraction orchestration + admin inspection.

    Two responsibilities:

    1. ``extract_and_store_from_text`` — the canonical entrypoint for
       running ``EventExtractionChain`` against any free-text input
       (chat turn, audio transcript, social post). Encapsulates dedupe,
       confidence override, and persistence.
    2. Admin/inspection helpers used by ``/internal/events/*`` and the
       GDPR memory wipe.

    Args:
        session: Async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = EventRepository(session)

    # ── Shared extract-and-store entrypoint ────────────────────────

    async def extract_and_store_from_text(
        self,
        *,
        llm: BaseChatModel,
        user_id: str,
        text: str,
        source: str,
        timezone: str | None,
        anchor_at: datetime | None,
        assistant_response: str | None = None,
        source_message_id: str | None = None,
        min_confidence: float = 0.6,
    ) -> list[UserEvent]:
        """Run ``EventExtractionChain`` against ``text`` and persist resolved events.

        All input channels (chat, audio, social) call this method. Same
        dedupe rules, same window/confidence filters, same source-tagging
        contract.

        Args:
            llm: LangChain chat model — caller supplies; service does not
                build its own to avoid duplicate provider initialisation.
            user_id: The user's unique identifier.
            text: The text to extract events from.
            source: Origin tag stored on each row (e.g. ``"conversation"``,
                ``"audio:<session_id>"``, ``"facebook"``).
            timezone: IANA tz name (``"America/Lima"`` fallback when None).
            anchor_at: UTC timestamp for relative-phrase resolution. Falls
                back to current UTC. Pass the message/post/chunk's
                creation time for accurate "tomorrow" handling.
            assistant_response: Optional assistant turn (chat only). Helps
                the chain pick up confirmations like "yes 3pm works".
            source_message_id: Optional foreign id (Rails Message id when
                source is conversation; AudioChunk id when audio; etc.).
            min_confidence: Confidence floor passed through to the chain.
                Defaults to 0.6; social ingest passes 0.7 for noisier text.

        Returns:
            List of newly persisted ``UserEvent`` schemas. Empty on
            extraction failure or when no events meet the filters.
        """
        if not text or not text.strip():
            return []

        tz = timezone or _DEFAULT_TIMEZONE
        now_utc = datetime.now(UTC)
        msg_at = anchor_at or now_utc
        chain = EventExtractionChain(llm=llm, min_confidence=min_confidence)

        try:
            resolved = await chain.extract(
                message=text,
                now_utc=now_utc,
                timezone=tz,
                message_created_at=msg_at,
                assistant_response=assistant_response,
            )
        except Exception:
            logger.exception(
                "Event extraction failed for user_id=%s source=%s",
                user_id,
                source,
            )
            return []

        if not resolved:
            return []

        stored: list[UserEvent] = []
        for ev in resolved:
            try:
                dup = await self._repo.find_duplicate(
                    user_id, title=ev.title, occurs_at=ev.occurs_at
                )
                if dup is not None:
                    logger.debug(
                        "Skipping duplicate event for user_id=%s source=%s: %r at %s",
                        user_id,
                        source,
                        ev.title,
                        ev.occurs_at.isoformat(),
                    )
                    continue
                row = await self._repo.create_event(
                    user_id=user_id,
                    title=ev.title,
                    occurs_at=ev.occurs_at,
                    occurs_at_has_time=ev.occurs_at_has_time,
                    raw_text=ev.raw_text,
                    source=source,
                    source_message_id=source_message_id,
                    confidence=ev.confidence,
                    timezone=tz,
                )
                stored.append(UserEvent.model_validate(row))
            except Exception:
                logger.exception(
                    "Event persist failed (continuing) user_id=%s source=%s title=%r",
                    user_id,
                    source,
                    ev.title,
                )
                continue

        if stored:
            logger.info(
                "Persisted %d/%d events for user_id=%s source=%s",
                len(stored),
                len(resolved),
                user_id,
                source,
            )
        return stored

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
