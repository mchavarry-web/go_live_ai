"""User-events admin endpoints.

Mirrors ``app/api/routes/memory.py`` for the ``user_events`` table. The
avatar's chat-time retrieval calls ``EventRepository`` directly via
``ChatService``; these endpoints exist for inspection, killing
hallucinated events, and GDPR symmetry.

Endpoints:
    GET    /internal/events/{user_id}                - List active upcoming events.
    GET    /internal/events/{user_id}/all            - List every event (debug).
    PATCH  /internal/events/{user_id}/{event_id}     - Update status (cancelled/archived).
    DELETE /internal/events/{user_id}                - Wipe all events (GDPR).

All routes are guarded by the ``X-Internal-Token`` header (applied at
router-include time in ``app/main.py``).
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DbSessionDep
from app.models.schemas import UserEvent
from app.services.event_service import EventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/events", tags=["Events"])


# ── Request/Response schemas ────────────────────────────────────────────


class UpdateEventStatusRequest(BaseModel):
    """Request body for ``PATCH /internal/events/{user_id}/{event_id}``."""

    status: Literal["active", "cancelled", "archived"] = Field(
        ...,
        description="New status for the event.",
    )


class EventListResponse(BaseModel):
    """Wrapped list of events with the user_id echoed back for clients."""

    user_id: str
    total: int
    events: list[UserEvent]


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    response_model=EventListResponse,
    summary="List active upcoming events",
    description="Return active events occurring within the next horizon_days (default 14).",
)
async def list_upcoming_events(
    user_id: str,
    session: DbSessionDep,
    horizon_days: int = 14,
    limit: int = 50,
) -> EventListResponse:
    """List upcoming active events for a user."""
    try:
        service = EventService(session=session)
        events = await service.list_upcoming(
            user_id, horizon_days=horizon_days, limit=limit
        )
        return EventListResponse(
            user_id=user_id, total=len(events), events=events
        )
    except Exception as exc:
        logger.exception("Event listing failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events.",
        ) from exc


@router.get(
    "/{user_id}/all",
    response_model=EventListResponse,
    summary="List every event (debug)",
    description="Return every event for the user, including cancelled and archived.",
)
async def list_all_events(
    user_id: str,
    session: DbSessionDep,
    limit: int = 200,
) -> EventListResponse:
    """Debug surface: every status, every age."""
    try:
        service = EventService(session=session)
        events = await service.list_all(user_id, limit=limit)
        return EventListResponse(
            user_id=user_id, total=len(events), events=events
        )
    except Exception as exc:
        logger.exception("Event debug listing failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events.",
        ) from exc


@router.patch(
    "/{user_id}/{event_id}",
    response_model=UserEvent,
    summary="Update event status",
    description="Flip an event between active / cancelled / archived. Used to kill hallucinated events.",
)
async def update_event_status(
    user_id: str,
    event_id: str,
    body: UpdateEventStatusRequest,
    session: DbSessionDep,
) -> UserEvent:
    """Update the status of a single event."""
    try:
        service = EventService(session=session)
        updated = await service.update_status(user_id, event_id, body.status)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Event status update failed: user_id=%s event_id=%s",
            user_id,
            event_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event status.",
        ) from exc


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all events for a user (GDPR)",
    description="Hard-delete every event for the user. Symmetric with the memory wipe.",
)
async def delete_user_events(
    user_id: str,
    session: DbSessionDep,
) -> None:
    """Delete all events for a user."""
    try:
        service = EventService(session=session)
        await service.delete_for_user(user_id)
    except Exception as exc:
        logger.exception("Event GDPR delete failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete events.",
        ) from exc
