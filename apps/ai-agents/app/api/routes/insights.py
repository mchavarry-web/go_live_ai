"""Insight extraction and search endpoints.

Provides endpoints for extracting insights from text and performing
semantic similarity searches across stored user insights.

Endpoints:
    POST /internal/insights/extract            - Extract insights from text.
    POST /internal/insights/extract-social      - Extract insights from social media data.
    POST /internal/insights/extract-instagram   - Extract insights from Instagram data.
    POST /internal/insights/search              - Semantic search across insights.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSessionDep, LLMDep, SettingsDep
from app.chains.insight_chain import InsightExtractionChain
from app.chains.instagram_content_chain import InstagramContentChain
from app.chains.instagram_interest_chain import InstagramInterestChain
from app.chains.instagram_social_chain import InstagramSocialGraphChain
from app.chains.social_insight_chain import SocialMediaInsightChain
from app.llm.providers import get_embeddings
from app.models.schemas import (
    InsightExtractRequest,
    InstagramExtractRequest,
    SemanticSearchRequest,
    SocialExtractRequest,
    Insight,
)
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/insights", tags=["Insights"])


@router.post(
    "/extract",
    summary="Extract insights from text",
    description=(
        "Analyze a user message and extract structured insights using "
        "the InsightExtractionChain with PydanticOutputParser."
    ),
)
async def extract_insights(
    request: InsightExtractRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Extract insights from a user message.

    Uses the InsightExtractionChain to analyze the message and
    extract structured insights with category, content, and
    confidence score. High-confidence insights are stored in the
    vector database.

    Args:
        request: The insight extraction request.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        Dict containing a list of extracted insights.

    Raises:
        HTTPException: If extraction fails.
    """
    try:
        # Extract insights using the chain
        chain = InsightExtractionChain(llm=llm)
        extracted = await chain.extract(
            message=request.message,
            context=request.context,
        )

        if not extracted:
            return {"insights": [], "stored": 0}

        # Store insights with embeddings
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        insight_dicts = [
            {
                "category": ins.category,
                "content": ins.content,
                "confidence": ins.confidence,
            }
            for ins in extracted
        ]

        stored = await memory_service.store_insights(
            user_id=request.user_id,
            insights=insight_dicts,
            source="manual_extraction",
        )

        # Build response
        stored_insights = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in stored
        ]

        return {
            "insights": [ins.model_dump() for ins in stored_insights],
            "stored": len(stored),
        }

    except Exception as exc:
        logger.exception("Insight extraction failed for user_id=%s", request.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insight extraction failed. Please try again.",
        ) from exc


@router.post(
    "/extract-social",
    summary="Extract insights from social media data",
    description=(
        "Analyze a user's social media footprint (profile + posts) using "
        "the SocialMediaInsightChain. Designed for batch analysis of tweets, "
        "posts, etc. Stores insights with the platform as source."
    ),
)
async def extract_social_insights(
    request: SocialExtractRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Extract insights from social media data using the specialized chain.

    Args:
        request: The social extraction request with platform, bio, and posts.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        Dict with extracted insights, count stored, and profile summary.

    Raises:
        HTTPException: If extraction fails.
    """
    try:
        chain = SocialMediaInsightChain(llm=llm)

        posts_data = [
            {
                "text": post.text,
                "is_repost": post.is_repost,
                "date": post.date,
                "media_types": post.media_types,
            }
            for post in request.posts
        ]

        result = await chain.extract(
            platform=request.platform,
            username=request.username,
            bio=request.bio,
            member_since=request.member_since,
            posts=posts_data,
        )

        if not result.insights:
            return {"insights": [], "stored": 0, "summary": result.summary}

        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        insight_dicts = [
            {
                "category": ins.category,
                "content": ins.content,
                "confidence": ins.confidence,
            }
            for ins in result.insights
        ]

        stored = await memory_service.store_insights(
            user_id=request.user_id,
            insights=insight_dicts,
            source=request.platform,
        )

        stored_insights = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in stored
        ]

        return {
            "insights": [ins.model_dump() for ins in stored_insights],
            "stored": len(stored),
            "summary": result.summary,
        }

    except Exception as exc:
        logger.exception(
            "Social insight extraction failed for user_id=%s, platform=%s",
            request.user_id,
            request.platform,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Social insight extraction failed. Please try again.",
        ) from exc


@router.post(
    "/extract-instagram",
    summary="Extract insights from Instagram data",
    description=(
        "Analyze a user's Instagram data (comments, topics, following, "
        "close friends, blocked) using 3 specialized chains in parallel. "
        "Stores insights with source='instagram'."
    ),
)
async def extract_instagram_insights(
    request: InstagramExtractRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Extract insights from Instagram data using 3 specialized chains.

    Runs InstagramContentChain, InstagramInterestChain, and
    InstagramSocialGraphChain in parallel for optimal performance.
    """
    try:
        content_chain = InstagramContentChain(llm=llm)
        interest_chain = InstagramInterestChain(llm=llm)
        social_chain = InstagramSocialGraphChain(llm=llm)

        comments_data = [
            {"text": c.text, "post_owner": c.post_owner}
            for c in request.comments
        ]

        content_result, interest_result, social_result = await asyncio.gather(
            content_chain.extract(comments=comments_data),
            interest_chain.extract(topics=request.topics, following=request.following),
            social_chain.extract(
                close_friends=request.close_friends,
                blocked=request.blocked,
                following_count=len(request.following),
            ),
        )

        all_insights = []
        for result in (content_result, interest_result, social_result):
            for ins in result.insights:
                all_insights.append({
                    "category": ins.category,
                    "content": ins.content,
                    "confidence": ins.confidence,
                })

        if not all_insights:
            summaries = [
                s for s in (
                    content_result.summary,
                    interest_result.summary,
                    social_result.summary,
                ) if s
            ]
            return {
                "insights": [],
                "stored": 0,
                "summary": " ".join(summaries),
            }

        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        stored = await memory_service.store_insights(
            user_id=request.user_id,
            insights=all_insights,
            source="instagram",
        )

        stored_insights = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in stored
        ]

        summaries = [
            s for s in (
                content_result.summary,
                interest_result.summary,
                social_result.summary,
            ) if s
        ]

        return {
            "insights": [ins.model_dump() for ins in stored_insights],
            "stored": len(stored),
            "summary": " ".join(summaries),
            "breakdown": {
                "content_insights": len(content_result.insights),
                "interest_insights": len(interest_result.insights),
                "social_graph_insights": len(social_result.insights),
            },
        }

    except Exception as exc:
        logger.exception(
            "Instagram insight extraction failed for user_id=%s",
            request.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Instagram insight extraction failed. Please try again.",
        ) from exc


@router.post(
    "/search",
    summary="Semantic search across insights",
    description="Search for semantically similar insights using vector similarity.",
)
async def search_insights(
    request: SemanticSearchRequest,
    settings: SettingsDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Search for similar insights using semantic similarity.

    Performs a vector similarity search in pgvector to find
    insights that are semantically related to the query.

    Args:
        request: The semantic search request with query and filters.
        settings: Application settings (injected).
        session: Async database session (injected).

    Returns:
        Dict containing matching insights sorted by similarity.

    Raises:
        HTTPException: If search fails.
    """
    try:
        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

        categories = (
            [cat.value for cat in request.categories]
            if request.categories
            else None
        )

        results = await memory_service.get_relevant_insights(
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k,
            categories=categories,
        )

        insights = [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            ).model_dump()
            for ins in results
        ]

        return {
            "insights": insights,
            "total": len(insights),
        }

    except Exception as exc:
        logger.exception("Insight search failed for user_id=%s", request.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insight search failed. Please try again.",
        ) from exc
