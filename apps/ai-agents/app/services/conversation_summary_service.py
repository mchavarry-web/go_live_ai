"""Conversation summarization orchestration.

Decides when to summarize (Phase 12 trigger), reads the prior summary,
calls ``ConversationSummaryChain``, and persists the result via
``ConversationSummaryRepository``. All logic that touches "should we
summarize this conversation now?" lives here so ``ChatService`` stays
agnostic.
"""

import logging

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.conversation_summary_chain import ConversationSummaryChain
from app.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)

logger = logging.getLogger(__name__)

# Trigger threshold: every Nth user turn we (re)summarize. 20 user turns
# is roughly 40 conversation entries (user + assistant), at which point
# the unsummarized tail starts to dominate the prompt's token budget.
DEFAULT_TURN_INTERVAL = 20


class ConversationSummaryService:
    """Orchestrate conversation summarization end-to-end.

    Args:
        session: Async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ConversationSummaryRepository(session)

    @staticmethod
    def should_summarize(
        *,
        turn_count: int,
        interval: int = DEFAULT_TURN_INTERVAL,
    ) -> bool:
        """Pure-function trigger so callers can decide before paying for I/O.

        We summarize when:
        - the user has reached at least one full interval (turn_count >= interval), AND
        - the current turn lands on the interval boundary (turn_count % interval == 0).

        Args:
            turn_count: Lifetime user-message count in this conversation.
            interval: How many user turns between summaries.

        Returns:
            True when this turn should kick off a summarization.
        """
        return turn_count >= interval and turn_count % interval == 0

    async def summarize_if_due(
        self,
        *,
        llm: BaseChatModel,
        user_id: str,
        conversation_id: str,
        conversation_history: list[dict[str, str]],
        display_name: str,
        turn_count: int,
        interval: int = DEFAULT_TURN_INTERVAL,
        range_end_message_id: str | None = None,
    ) -> bool:
        """Run summarization when the trigger says yes; no-op otherwise.

        Idempotent: if a summary already exists with the same
        ``range_end_message_id``, we skip rather than write a duplicate
        row. (Cheap protection against double-firing post-turn tasks.)

        Args:
            llm: LangChain chat model.
            user_id: The user's unique identifier.
            conversation_id: Rails Conversation id.
            conversation_history: Full message history sent in the request.
            display_name: User's display name for the prompt.
            turn_count: Lifetime user-message count.
            interval: Trigger interval (default 20).
            range_end_message_id: Optional Rails id of the final message
                in this window. Phase 13 uses it to align history truncation.

        Returns:
            True if a new summary row was persisted; False on no-op.
        """
        if not self.should_summarize(turn_count=turn_count, interval=interval):
            return False
        if not conversation_history:
            return False

        prior = await self._repo.latest_for_conversation(conversation_id)
        if prior is not None and prior.range_end_message_id == range_end_message_id and range_end_message_id is not None:
            logger.debug(
                "summary skip — already up-to-date conv=%s end=%s",
                conversation_id,
                range_end_message_id,
            )
            return False

        chain = ConversationSummaryChain(llm=llm)
        try:
            result = await chain.summarize(
                conversation_history=conversation_history,
                prior_summary=(prior.summary if prior else ""),
                display_name=display_name,
            )
        except Exception:
            logger.exception(
                "Conversation summarization failed conv=%s user=%s",
                conversation_id,
                user_id,
            )
            return False

        await self._repo.supersede_then_create(
            user_id=user_id,
            conversation_id=conversation_id,
            summary=result.summary,
            message_count=len(conversation_history),
            summary_token_count=result.token_count_estimate or max(1, len(result.summary) // 4),
            range_start_message_id=(prior.range_end_message_id if prior else None),
            range_end_message_id=range_end_message_id,
        )
        return True

    async def latest_summary_text(
        self,
        conversation_id: str,
    ) -> str | None:
        """Convenience for read-side callers that only want the text."""
        row = await self._repo.latest_for_conversation(conversation_id)
        return row.summary if row else None

    async def delete_for_user(self, user_id: str) -> int:
        return await self._repo.delete_by_user_id(user_id)
