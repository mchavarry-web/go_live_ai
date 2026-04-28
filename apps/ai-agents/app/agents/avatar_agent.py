"""LangChain Agent for avatar interactions with real-time web search.

Extends the basic AvatarChain with tool-calling capabilities using
LangGraph's create_react_agent. The agent autonomously decides when to call
the web_search tool based on the user's message and the instructions
in the system prompt.

Supports both complete and streaming response generation, maintaining
full compatibility with the existing ChatService interface.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langsmith import traceable
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

# Each tool call occupies 2 graph steps (invoke + result) plus 2 for the
# initial LLM call and the final answer. With a cap of 5 tool calls:
# 5 * 2 + 2 = 12. Add a small buffer → 16.
# GraphRecursionError is the hard safety net if the model ignores prompt limits.
_MAX_TOOL_CALLS = 5
_AGENT_RECURSION_LIMIT = _MAX_TOOL_CALLS * 2 + 6  # = 16


def _build_history_messages(
    conversation_history: list[dict[str, str]] | None,
) -> list[BaseMessage]:
    """Convert conversation history dicts to LangChain message objects.

    Args:
        conversation_history: List of ``{"role": ..., "content": ...}`` dicts.

    Returns:
        Ordered list of LangChain message objects.
    """
    if not conversation_history:
        return []

    messages: list[BaseMessage] = []
    for entry in conversation_history:
        role = entry.get("role", "").lower()
        content = entry.get("content", "")
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            logger.warning("Skipping unknown message role: %s", role)
    return messages


class AvatarAgent:
    """LangGraph agent for avatar conversations with tool-calling support.

    Wraps a CompiledStateGraph (create_react_agent) that can autonomously
    invoke tools (e.g. web_search) when the LLM determines they are needed.
    The agent uses the same system prompt as AvatarChain, extended with
    instructions for proactive web search usage.

    Attributes:
        llm: The LangChain chat model instance (must support tool-calling).
        tools: List of LangChain tools available to the agent.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        max_tool_calls: int = _MAX_TOOL_CALLS,
    ) -> None:
        """Initialize the avatar agent with tool-calling support.

        Args:
            llm: A LangChain BaseChatModel that supports tool-calling
                (ChatOpenAI, ChatAnthropic, etc.).
            tools: List of LangChain tools the agent can invoke.
            max_tool_calls: Maximum number of tool calls allowed per turn.
                Drives the LangGraph recursion_limit (max_tool_calls * 2 + 6).
        """
        self.llm = llm
        self.tools = tools
        self.recursion_limit = max_tool_calls * 2 + 6
        self._graph = create_react_agent(model=llm, tools=tools)

    @traceable(name="avatar_agent_generate", run_type="chain")
    async def generate(
        self,
        message: str,
        system_prompt: str,
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> str:
        """Generate a complete avatar response using the agent.

        Args:
            message: The user's current message.
            system_prompt: The fully built system prompt string.
            conversation_history: Recent messages as role/content dicts.

        Returns:
            The agent's final response string.

        Raises:
            Exception: Propagates any agent or LLM errors.
        """
        history_messages = _build_history_messages(conversation_history)

        # Build message list: system prompt → history (excluding current turn) → current message.
        # conversation_history may already include the current user message as its last entry
        # (sent by api-backend for context). Strip it if so to avoid sending it twice.
        if history_messages and isinstance(history_messages[-1], HumanMessage):
            history_messages = history_messages[:-1]

        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(history_messages)
        messages.append(HumanMessage(content=message))

        logger.info(
            "Avatar agent generating response: history_len=%d",
            len(history_messages),
        )

        try:
            result = await self._graph.ainvoke(
                {"messages": messages},
                config={"recursion_limit": self.recursion_limit},
            )
            output_messages = result.get("messages", [])
        except GraphRecursionError as exc:
            logger.warning(
                "Avatar agent reached recursion limit — extracting partial response"
            )
            # LangGraph adjunta el estado parcial en la excepción
            partial = getattr(exc, "state", None) or {}
            output_messages = partial.get("messages", [])

        # Exclude AIMessages that carry tool_calls — those are intermediate
        # planning steps, not the final answer. The last AIMessage without
        # tool_calls and with non-empty content is always the final response.
        ai_messages = [
            m for m in output_messages
            if isinstance(m, AIMessage)
            and m.content
            and not getattr(m, "tool_calls", None)
        ]
        output = ai_messages[-1].content if ai_messages else (
            "Busqué bastante pero no encontré información concluyente sobre eso. "
            "Puede que el dato no esté disponible aún o que los resultados no sean precisos."
        )

        logger.info("Avatar agent response generated: response_len=%d", len(output))
        return output

    @traceable(name="avatar_agent_generate_stream", run_type="chain")
    async def generate_stream(
        self,
        message: str,
        system_prompt: str,
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream avatar response tokens from the agent.

        Uses ``astream_events`` to capture LLM token chunks while the agent
        may be performing tool calls in between. Only the final LLM response
        tokens are yielded — intermediate tool call outputs are suppressed.

        Args:
            message: The user's current message.
            system_prompt: The fully built system prompt string.
            conversation_history: Recent messages as role/content dicts.

        Yields:
            Individual token strings as they arrive from the LLM.

        Raises:
            Exception: Propagates any agent or LLM errors.
        """
        history_messages = _build_history_messages(conversation_history)

        # Strip the last message if it's a HumanMessage duplicating the current turn.
        if history_messages and isinstance(history_messages[-1], HumanMessage):
            history_messages = history_messages[:-1]

        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(history_messages)
        messages.append(HumanMessage(content=message))

        logger.info(
            "Avatar agent starting streaming response: history_len=%d",
            len(history_messages),
        )

        input_data = {"messages": messages}

        # Collect tokens grouped by LLM run_id so we can detect which runs
        # ended up being tool calls (they emit on_chat_model_end with tool_calls)
        # and discard them, yielding only the tokens of the final answer run.
        # GraphRecursionError se captura para devolver un mensaje de fallback
        # en lugar de propagar el error al usuario.
        #
        # Strategy:
        #   - Buffer tokens per run_id during on_chat_model_stream.
        #   - On on_chat_model_end, check if the finished message has tool_calls.
        #     If it does, discard the buffer for that run_id.
        #     If it doesn't, yield the buffered tokens immediately.
        token_buffer: dict[str, list[str]] = {}
        tool_call_run_ids: set[str] = set()

        try:
            async for event in self._graph.astream_events(
                input_data,
                version="v2",
                config={"recursion_limit": self.recursion_limit},
            ):
                event_type = event.get("event")
                run_id = event.get("run_id", "")

                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk or not hasattr(chunk, "content") or not chunk.content:
                        continue
                    # Skip tool_call_chunks (argument tokens, not text)
                    if getattr(chunk, "tool_call_chunks", None):
                        tool_call_run_ids.add(run_id)
                        continue
                    token_buffer.setdefault(run_id, []).append(chunk.content)

                elif event_type == "on_chat_model_end":
                    output_msg = event.get("data", {}).get("output")
                    has_tool_calls = bool(
                        output_msg and getattr(output_msg, "tool_calls", None)
                    )
                    if has_tool_calls:
                        # This LLM turn was a tool call decision — discard its tokens.
                        tool_call_run_ids.add(run_id)
                        token_buffer.pop(run_id, None)
                    else:
                        # This LLM turn is a real text response.
                        buffered = token_buffer.pop(run_id, [])
                        if buffered:
                            for token in buffered:
                                yield token
                        else:
                            # Some models (notably OpenAI reasoning models like
                            # o1/o3/o4-mini) don't emit per-token chunks during
                            # streaming — content only arrives in the final message.
                            # Fall back to yielding the full content so the user
                            # sees a response instead of an empty stream.
                            content = getattr(output_msg, "content", "") if output_msg else ""
                            if content:
                                yield content

        except GraphRecursionError:
            logger.warning(
                "Avatar agent streaming reached recursion limit — yielding fallback"
            )
            yield (
                "Busqué bastante pero no encontré información concluyente sobre eso. "
                "Puede que el dato no esté disponible aún o que los resultados no sean precisos."
            )
        except Exception:
            logger.exception("Avatar agent streaming failed")
            raise
