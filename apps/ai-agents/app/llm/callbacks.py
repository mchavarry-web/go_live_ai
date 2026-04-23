"""Custom LangChain callback handlers.

Provides callback handlers for token counting and logging across
chain invocations. These complement LangSmith's automatic tracing
with application-level metrics.
"""

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class TokenCounterCallback(AsyncCallbackHandler):
    """Callback to track token usage across chain invocations.

    Accumulates prompt, completion, and total token counts from
    each LLM call. Use ``reset()`` to clear counters between requests.

    Attributes:
        total_prompt_tokens: Cumulative prompt tokens used.
        total_completion_tokens: Cumulative completion tokens used.
        total_tokens: Cumulative total tokens used.
    """

    def __init__(self) -> None:
        """Initialize token counters to zero."""
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Track token usage when an LLM call completes.

        Args:
            response: The LLM result containing output and metadata.
            run_id: Unique identifier for this run.
            parent_run_id: Identifier of the parent run, if any.
            **kwargs: Additional keyword arguments.
        """
        if response.llm_output and "token_usage" in response.llm_output:
            usage: dict[str, int] = response.llm_output["token_usage"]
            self.total_prompt_tokens += usage.get("prompt_tokens", 0)
            self.total_completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)

    def reset(self) -> None:
        """Reset all token counters to zero."""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0


class LoggingCallback(AsyncCallbackHandler):
    """Callback to log chain execution events.

    Logs chain start, end, and error events for debugging and
    monitoring purposes. Works alongside LangSmith tracing.
    """

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log when a chain starts executing.

        Args:
            serialized: Serialized chain metadata.
            inputs: Input data for the chain.
            run_id: Unique identifier for this run.
            parent_run_id: Identifier of the parent run, if any.
            **kwargs: Additional keyword arguments.
        """
        chain_name = serialized.get("name", "unknown") if serialized else "unknown"
        logger.info("Chain started: %s (run_id=%s)", chain_name, run_id)

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log when a chain encounters an error.

        Args:
            error: The exception that occurred.
            run_id: Unique identifier for this run.
            parent_run_id: Identifier of the parent run, if any.
            **kwargs: Additional keyword arguments.
        """
        logger.error("Chain error (run_id=%s): %s", run_id, str(error))

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log when an LLM call completes.

        Args:
            response: The LLM result containing output and metadata.
            run_id: Unique identifier for this run.
            parent_run_id: Identifier of the parent run, if any.
            **kwargs: Additional keyword arguments.
        """
        generation_count = sum(len(gens) for gens in response.generations)
        logger.debug(
            "LLM completed (run_id=%s): %d generation(s)",
            run_id,
            generation_count,
        )
