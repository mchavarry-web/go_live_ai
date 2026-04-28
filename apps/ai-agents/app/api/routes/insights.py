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
from app.chains.facebook_content_chain import FacebookContentChain
from app.chains.facebook_social_chain import FacebookSocialChain
from app.chains.insight_chain import InsightExtractionChain
from app.chains.instagram_content_chain import InstagramContentChain
from app.chains.instagram_interest_chain import InstagramInterestChain
from app.chains.instagram_social_chain import InstagramSocialGraphChain
from app.chains.social_insight_chain import SocialMediaInsightChain
from app.chains.spotify_taste_chain import SpotifyTasteChain
from app.chains.twitter_content_chain import TwitterContentChain
from app.chains.twitter_interest_chain import TwitterInterestChain
from app.llm.providers import get_embeddings
from app.models.schemas import (
    Insight,
    InsightExtractRequest,
    InstagramExtractRequest,
    SemanticSearchRequest,
    SocialExtractRequest,
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
        "Analyze a user's social media footprint and store the resulting "
        "insights tagged with the platform as source. Dispatches to a "
        "platform-specific chain when known: Facebook (content+social), "
        "Twitter (content+interest), Spotify (taste). Falls back to the "
        "generic SocialMediaInsightChain for any other platform."
    ),
)
async def extract_social_insights(
    request: SocialExtractRequest,
    settings: SettingsDep,
    llm: LLMDep,
    session: DbSessionDep,
) -> dict[str, object]:
    """Extract insights from social media data, dispatched per-platform.

    Routing:
      - facebook → FacebookContentChain + FacebookSocialChain (parallel)
      - twitter  → TwitterContentChain + TwitterInterestChain (parallel)
      - spotify  → SpotifyTasteChain
      - other    → generic SocialMediaInsightChain (legacy posts/bio shape)

    The per-platform chains read `request.data` (raw provider payload as
    stashed on Rails' SocialConnection.metadata.raw_data). The generic
    chain reads `request.posts` / `request.bio` / `request.member_since`.

    Args:
        request: The social extraction request.
        settings: Application settings (injected).
        llm: LangChain LLM instance (injected).
        session: Async database session (injected).

    Returns:
        Dict with extracted insights, count stored, and profile summary.

    Raises:
        HTTPException: If extraction fails.
    """
    platform = (request.platform or "").lower()
    try:
        if platform == "facebook":
            insight_dicts, summary, breakdown = await _extract_facebook(llm, request.data)
        elif platform == "twitter":
            insight_dicts, summary, breakdown = await _extract_twitter(llm, request.data)
        elif platform == "spotify":
            insight_dicts, summary, breakdown = await _extract_spotify(llm, request.data)
        else:
            insight_dicts, summary, breakdown = await _extract_generic(llm, request)

        if not insight_dicts:
            return {
                "insights": [],
                "stored": 0,
                "summary": summary,
                **({"breakdown": breakdown} if breakdown else {}),
            }

        embeddings = get_embeddings(settings)
        memory_service = MemoryService(session=session, embeddings=embeddings)

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
            "summary": summary,
            "insights_count": len(stored),
            **({"breakdown": breakdown} if breakdown else {}),
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


# ── Per-platform extractors ────────────────────────────────────────────
# Each returns (insight_dicts, summary, breakdown_or_none). `insight_dicts`
# is a list shaped like {category, content, confidence} ready for
# MemoryService.store_insights.


async def _extract_facebook(
    llm: object, data: dict[str, object]
) -> tuple[list[dict[str, object]], str, dict[str, int] | None]:
    content_chain = FacebookContentChain(llm=llm)
    social_chain = FacebookSocialChain(llm=llm)

    content_result, social_result = await asyncio.gather(
        content_chain.extract(payload=data),
        social_chain.extract(payload=data),
    )

    insight_dicts: list[dict[str, object]] = [
        {
            "category": ins.category,
            "content": ins.content,
            "confidence": ins.confidence,
        }
        for ins in content_result.insights
    ]
    # Social ties → relationship insights with the tie kind as evidence.
    for tie in social_result.ties:
        insight_dicts.append({
            "category": "relationship",
            "content": f"{tie.name} ({tie.kind})",
            "confidence": tie.confidence,
        })

    breakdown = {
        "content_insights": len(content_result.insights),
        "social_ties": len(social_result.ties),
        "group_interests": len(social_result.group_interests),
    }
    return insight_dicts, "", breakdown


async def _extract_twitter(
    llm: object, data: dict[str, object]
) -> tuple[list[dict[str, object]], str, dict[str, int] | None]:
    content_chain = TwitterContentChain(llm=llm)
    interest_chain = TwitterInterestChain(llm=llm)

    content_result, interest_result = await asyncio.gather(
        content_chain.extract(payload=data),
        interest_chain.extract(payload=data),
    )

    insight_dicts: list[dict[str, object]] = [
        {
            "category": ins.category,
            "content": ins.content,
            "confidence": ins.confidence,
        }
        for ins in content_result.insights
    ]
    for interest in interest_result.interests:
        insight_dicts.append({
            "category": "interest",
            "content": interest.topic,
            "confidence": interest.weight,
        })

    breakdown = {
        "content_insights": len(content_result.insights),
        "interests": len(interest_result.interests),
    }
    return insight_dicts, "", breakdown


async def _extract_spotify(
    llm: object, data: dict[str, object]
) -> tuple[list[dict[str, object]], str, dict[str, int] | None]:
    chain = SpotifyTasteChain(llm=llm)
    result = await chain.extract(payload=data)

    insight_dicts: list[dict[str, object]] = [
        {
            "category": f"taste:{taste.axis}",
            "content": taste.value,
            "confidence": taste.confidence,
        }
        for taste in result.taste
    ]
    if result.top_genres:
        insight_dicts.append({
            "category": "preference",
            "content": "Géneros dominantes: " + ", ".join(result.top_genres[:8]),
            "confidence": 0.9,
        })

    breakdown = {
        "taste_axes": len(result.taste),
        "top_genres": len(result.top_genres),
    }
    return insight_dicts, result.summary, breakdown


async def _extract_generic(
    llm: object, request: SocialExtractRequest
) -> tuple[list[dict[str, object]], str, dict[str, int] | None]:
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
    insight_dicts: list[dict[str, object]] = [
        {
            "category": ins.category,
            "content": ins.content,
            "confidence": ins.confidence,
        }
        for ins in result.insights
    ]
    return insight_dicts, result.summary, None


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
