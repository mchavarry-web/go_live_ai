"""Insight service for extraction and semantic search.

Coordinates InsightExtractionChain, MemoryService, and embeddings
for extracting insights from text and performing semantic searches.
"""

import logging

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.insight_chain import InsightExtractionChain
from app.models.schemas import Insight
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class InsightService:
    """Service for insight extraction and search operations.

    Coordinates the InsightExtractionChain for extracting insights
    and MemoryService for storage and retrieval.

    Attributes:
        extraction_chain: LangChain chain for insight extraction.
        memory_service: Service for memory operations.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        embeddings: Embeddings,
        session: AsyncSession,
    ) -> None:
        """Initialize the insight service.

        Args:
            llm: LangChain LLM instance for extraction.
            embeddings: LangChain Embeddings for vector generation.
            session: Async database session.
        """
        self.extraction_chain = InsightExtractionChain(llm=llm)
        self.memory_service = MemoryService(session=session, embeddings=embeddings)

    async def extract_and_store(
        self,
        user_id: str,
        message: str,
        context: str = "",
    ) -> list[Insight]:
        """Extract insights from a message and store them.

        Args:
            user_id: The user's unique identifier.
            message: The text to extract insights from.
            context: Optional prior context about the user.

        Returns:
            List of Insight schemas for stored insights.
        """
        extracted = await self.extraction_chain.extract(
            message=message,
            context=context,
        )

        if not extracted:
            return []

        insight_dicts = [
            {
                "category": ins.category,
                "content": ins.content,
                "confidence": ins.confidence,
            }
            for ins in extracted
        ]

        stored = await self.memory_service.store_insights(
            user_id=user_id,
            insights=insight_dicts,
            source="manual_extraction",
        )

        return [
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

    async def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        categories: list[str] | None = None,
    ) -> list[Insight]:
        """Search for relevant insights using semantic similarity.

        Args:
            user_id: The user's unique identifier.
            query: The search query.
            top_k: Number of results to return.
            categories: Optional category filter.

        Returns:
            List of Insight schemas matching the query.
        """
        results = await self.memory_service.get_relevant_insights(
            user_id=user_id,
            query=query,
            top_k=top_k,
            categories=categories,
        )

        return [
            Insight(
                id=ins.id,
                user_id=ins.user_id,
                category=ins.category,
                content=ins.content,
                confidence=ins.confidence,
                source=ins.source,
                created_at=ins.created_at,
            )
            for ins in results
        ]
