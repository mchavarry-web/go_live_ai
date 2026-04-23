"""Memory management endpoints.

Provides endpoints for retrieving, managing, and deleting user
memory stored in the vector database. Supports GDPR-compliant
data deletion and individual insight CRUD.

Endpoints:
    GET    /internal/memory/{user_id}                         - Get user memory summary.
    DELETE /internal/memory/{user_id}                         - Delete all user memory (GDPR).
    GET    /internal/memory/{user_id}/categories              - Get insight counts by category.
    DELETE /internal/memory/{user_id}/insights/{insight_id}   - Delete a single insight.
    PATCH  /internal/memory/{user_id}/insights/{insight_id}   - Update a single insight.
    POST   /internal/memory/{user_id}/teach                   - Manually add an insight.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DbSessionDep, SettingsDep
from app.llm.providers import get_embeddings
from app.models.schemas import Insight, MemoryResponse
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/memory", tags=["Memory"])


# ── Request/Response schemas ────────────────────────────────────────────


class UpdateInsightRequest(BaseModel):
    """Request to update a single insight's content."""

    content: str = Field(..., min_length=1, max_length=1000)


class TeachInsightRequest(BaseModel):
    """Request to manually teach the avatar a new fact."""

    content: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(default="preference")


class CategoryCountsResponse(BaseModel):
    """Response with insight counts per category."""

    user_id: str
    counts: dict[str, int]
    total: int


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/{user_id}",
    response_model=MemoryResponse,
    summary="Get user memory",
    description="Retrieve the memory summary for a user including insights and knowledge level.",
)
async def get_user_memory(
    user_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> MemoryResponse:
    """Get the memory summary for a specific user."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        return await memory_service.get_user_memory(user_id)
    except Exception as exc:
        logger.exception("Memory retrieval failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory retrieval failed. Please try again.",
        ) from exc


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user memory (GDPR)",
    description="Delete all stored memory and insights for a user. GDPR compliance.",
)
async def delete_user_memory(
    user_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> None:
    """Delete all memory for a user (GDPR compliance)."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        await memory_service.delete_user_memory(user_id)
    except Exception as exc:
        logger.exception("Memory deletion failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory deletion failed. Please try again.",
        ) from exc


@router.get(
    "/{user_id}/categories",
    response_model=CategoryCountsResponse,
    summary="Get insight counts by category",
    description="Returns the number of insights per category for a user.",
)
async def get_insights_by_category(
    user_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> CategoryCountsResponse:
    """Get insight counts grouped by category."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        counts = await memory_service.get_insights_by_category(user_id)
        total = sum(counts.values())
        return CategoryCountsResponse(user_id=user_id, counts=counts, total=total)
    except Exception as exc:
        logger.exception("Category counts failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve category counts.",
        ) from exc


@router.get(
    "/{user_id}/sources",
    summary="Get insight counts by source",
    description="Returns the number of insights per source (conversation, twitter, etc.) for a user.",
)
async def get_insights_by_source(
    user_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Get insight counts grouped by source."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        sources = await memory_service.get_insights_by_source(user_id)
        total = sum(sources.values())
        return {"user_id": user_id, "sources": sources, "total": total}
    except Exception as exc:
        logger.exception("Source counts failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve source counts.",
        ) from exc


@router.delete(
    "/{user_id}/insights/{insight_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single insight",
    description="Delete a specific insight by ID for a user.",
)
async def delete_single_insight(
    user_id: str,
    insight_id: str,
    settings: SettingsDep,
    session: DbSessionDep,
) -> None:
    """Delete a single insight for a user."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        deleted = await memory_service.delete_insight(user_id, insight_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight not found.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Delete insight failed: user_id=%s, insight_id=%s", user_id, insight_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete insight.",
        ) from exc


@router.patch(
    "/{user_id}/insights/{insight_id}",
    response_model=Insight,
    summary="Update a single insight",
    description="Update the content of a specific insight. Regenerates its embedding.",
)
async def update_single_insight(
    user_id: str,
    insight_id: str,
    body: UpdateInsightRequest,
    settings: SettingsDep,
    session: DbSessionDep,
) -> Insight:
    """Update the content of a single insight."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        updated = await memory_service.update_insight(user_id, insight_id, body.content)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight not found.",
            )
        return Insight(
            id=updated.id,
            user_id=updated.user_id,
            category=updated.category,
            content=updated.content,
            confidence=updated.confidence,
            source=updated.source,
            created_at=updated.created_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Update insight failed: user_id=%s, insight_id=%s", user_id, insight_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update insight.",
        ) from exc


@router.post(
    "/{user_id}/teach",
    response_model=Insight,
    status_code=status.HTTP_201_CREATED,
    summary="Manually teach the avatar",
    description="Add a new insight manually (source: manual).",
)
async def teach_avatar(
    user_id: str,
    body: TeachInsightRequest,
    settings: SettingsDep,
    session: DbSessionDep,
) -> Insight:
    """Manually add an insight for the avatar to remember."""
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)
        results = await memory_service.store_insights(
            user_id=user_id,
            insights=[
                {
                    "content": body.content,
                    "category": body.category,
                    "confidence": 1.0,
                }
            ],
            source="manual",
        )
        if not results:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store insight.",
            )
        ins = results[0]
        return Insight(
            id=ins.id,
            user_id=ins.user_id,
            category=ins.category,
            content=ins.content,
            confidence=ins.confidence,
            source=ins.source,
            created_at=ins.created_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Teach avatar failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to teach avatar.",
        ) from exc
