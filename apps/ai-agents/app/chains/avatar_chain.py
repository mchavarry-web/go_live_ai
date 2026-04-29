"""Avatar conversation chain using LangChain.

Orchestrates the avatar's response generation using ChatPromptTemplate,
LLM invocation, and message handling. Supports both complete and streaming
responses. All invocations are traced via LangSmith.

When web_search is enabled in settings, delegates to AvatarAgent (an
AgentExecutor with tool-calling) instead of the bare prompt | llm chain.
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langsmith import traceable

from app.config.settings import Settings
from app.llm.callbacks import LoggingCallback, TokenCounterCallback
from app.prompts.avatar_prompts import build_avatar_system_prompt, get_avatar_chat_prompt

logger = logging.getLogger(__name__)


def _build_history_messages(
    conversation_history: list[dict[str, str]] | None,
) -> list[BaseMessage]:
    """Convert conversation history dicts to LangChain message objects.

    Each dict must contain ``role`` (``"user"`` or ``"assistant"``) and
    ``content`` keys. Unknown roles are silently skipped.

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


def _get_current_datetime() -> str:
    """Return a human-readable string of the current local date and time.

    Returns:
        A formatted string like "jueves 26 de marzo de 2026, 14:32 hs".
    """
    now = datetime.now()
    # Locale-independent Spanish format
    day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    month_names = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    day_name = day_names[now.weekday()]
    month_name = month_names[now.month - 1]
    return f"{day_name} {now.day} de {month_name} de {now.year}, {now.strftime('%H:%M')} hs"


class AvatarChain:
    """LangChain chain for avatar conversation generation.

    Composes a system prompt from user profile data, injects conversation
    history and current datetime, then invokes the LLM to produce a response.

    When ``settings.web_search_enabled`` is True, delegates to an
    ``AvatarAgent`` backed by an ``AgentExecutor`` with a ``web_search``
    tool so the LLM can proactively fetch real-time information.

    When ``settings.web_search_enabled`` is False, falls back to the
    original ``prompt | llm`` chain with no tool-calling overhead.

    Attributes:
        llm: The LangChain chat model instance.
        settings: Application configuration.
    """

    def __init__(self, llm: BaseChatModel, settings: Settings) -> None:
        """Initialize the avatar chain.

        Args:
            llm: A LangChain BaseChatModel (ChatOpenAI, ChatAnthropic, etc.).
            settings: Application settings for configuration.
        """
        self.llm = llm
        self.settings = settings
        self.prompt_template = get_avatar_chat_prompt()
        self._agent = self._build_agent() if settings.web_search_enabled else None

    def _build_agent(self):
        """Instantiate AvatarAgent with the configured web search tool.

        Returns:
            An AvatarAgent instance, or None if tool building fails.
        """
        try:
            from app.agents.avatar_agent import AvatarAgent
            from app.tools.web_search import (
                build_fetch_urls_tool,
                build_web_search_tool,
            )

            tavily_key = self.settings.tavily_api_key.get_secret_value()
            web_search = build_web_search_tool(
                tavily_api_key=tavily_key or None,
                max_results=self.settings.web_search_max_results,
            )
            tools = [web_search]
            fetch_urls = build_fetch_urls_tool(
                tavily_api_key=tavily_key or None,
                max_urls=self.settings.fetch_url_max_urls,
            )
            if fetch_urls is not None:
                tools.append(fetch_urls)
            logger.info(
                "Web search enabled: provider=%s, max_results=%d, fetch_urls=%s",
                "tavily" if tavily_key else "duckduckgo",
                self.settings.web_search_max_results,
                fetch_urls is not None,
            )
            return AvatarAgent(
                llm=self.llm,
                tools=tools,
                max_tool_calls=self.settings.web_search_max_calls,
            )
        except Exception:
            logger.exception(
                "Failed to build AvatarAgent — falling back to chain without tools"
            )
            return None

    def _build_system_prompt(self, user_profile: dict) -> str:
        """Build the full system prompt including current datetime.

        Args:
            user_profile: Dict with avatar and user profile data.

        Returns:
            Fully formatted system prompt string.
        """
        return build_avatar_system_prompt(
            avatar_name=user_profile.get("avatar_name", "Avatar"),
            display_name=user_profile.get("display_name", "Usuario"),
            knowledge_level=user_profile.get("knowledge_level", 1),
            age_range=user_profile.get("age_range"),
            interests=user_profile.get("interests"),
            introvert_extrovert=user_profile.get("introvert_extrovert"),
            rational_emotional=user_profile.get("rational_emotional"),
            values=user_profile.get("values"),
            social_data=user_profile.get("social_data"),
            health_data=user_profile.get("health_data"),
            insights=user_profile.get("insights"),
            persona_insights=user_profile.get("persona_insights"),
            behavior_settings=user_profile.get("behavior_settings"),
            current_datetime=_get_current_datetime(),
            country=user_profile.get("country"),
            formality_level=user_profile.get("formality_level"),
            custom_expressions=user_profile.get("custom_expressions"),
            active_mode=user_profile.get("active_mode", "friends"),
            mode_message_count=user_profile.get("mode_message_count", 0),
        )

    @traceable(name="avatar_generate", run_type="chain")
    async def generate(
        self,
        message: str,
        user_profile: dict,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> dict:
        """Generate a complete avatar response.

        Delegates to AvatarAgent when web_search is enabled, otherwise
        uses the bare ``prompt | llm`` chain.

        Args:
            message: The user's current message.
            user_profile: Dict with avatar_name, display_name, knowledge_level,
                age_range, interests, plus optional social_data, health_data,
                and insights.
            conversation_history: Recent messages as role/content dicts.

        Returns:
            Dict with ``response`` (str) and ``tokens_used`` (int) keys.
        """
        system_prompt = self._build_system_prompt(user_profile)

        # --- Agent path (with web search tool-calling) ---
        if self._agent is not None:
            logger.info(
                "Generating avatar response via agent: user=%s, history_len=%d",
                user_profile.get("display_name", "unknown"),
                len(conversation_history or []),
            )
            try:
                response_text = await self._agent.generate(
                    message=message,
                    system_prompt=system_prompt,
                    conversation_history=conversation_history,
                )
                return {"response": response_text, "tokens_used": 0}
            except Exception:
                logger.exception(
                    "Agent generation failed, falling back to chain: user=%s",
                    user_profile.get("display_name", "unknown"),
                )
                # Fall through to chain as last resort

        # --- Chain path (without tools, original behavior) ---
        token_counter = TokenCounterCallback()
        logging_callback = LoggingCallback()

        history_messages = _build_history_messages(conversation_history)

        prompt_input = {
            "system_prompt": system_prompt,
            "history": history_messages,
            "user_message": message,
        }

        chain = self.prompt_template | self.llm

        logger.info(
            "Generating avatar response via chain: user=%s, history_len=%d",
            user_profile.get("display_name", "unknown"),
            len(history_messages),
        )

        try:
            response = await chain.ainvoke(
                prompt_input,
                config={"callbacks": [token_counter, logging_callback]},
            )
        except Exception:
            logger.exception("LLM invocation failed during avatar generation")
            raise

        response_text = response.content if hasattr(response, "content") else str(response)
        tokens_used = token_counter.total_tokens

        logger.info(
            "Avatar response generated: tokens_used=%d, response_len=%d",
            tokens_used,
            len(response_text),
        )

        return {
            "response": response_text,
            "tokens_used": tokens_used,
        }

    @traceable(name="avatar_generate_stream", run_type="chain")
    async def generate_stream(
        self,
        message: str,
        user_profile: dict,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream avatar response tokens as they arrive.

        Delegates to AvatarAgent.generate_stream when web_search is enabled,
        otherwise uses the bare ``prompt | llm`` chain with ``astream()``.

        Args:
            message: The user's current message.
            user_profile: Dict with avatar profile and context data.
            conversation_history: Recent messages as role/content dicts.

        Yields:
            Individual token strings as they arrive from the LLM.
        """
        system_prompt = self._build_system_prompt(user_profile)

        # --- Agent path (with web search tool-calling) ---
        if self._agent is not None:
            logger.info(
                "Starting streaming avatar response via agent: user=%s",
                user_profile.get("display_name", "unknown"),
            )
            try:
                async for token in self._agent.generate_stream(
                    message=message,
                    system_prompt=system_prompt,
                    conversation_history=conversation_history,
                ):
                    yield token
                return
            except Exception:
                logger.exception(
                    "Agent streaming failed, falling back to chain: user=%s",
                    user_profile.get("display_name", "unknown"),
                )
                # Fall through to chain as last resort

        # --- Chain path (without tools, original behavior) ---
        history_messages = _build_history_messages(conversation_history)

        prompt_input = {
            "system_prompt": system_prompt,
            "history": history_messages,
            "user_message": message,
        }

        chain = self.prompt_template | self.llm

        logger.info(
            "Starting streaming avatar response via chain: user=%s",
            user_profile.get("display_name", "unknown"),
        )

        try:
            async for chunk in chain.astream(prompt_input):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    yield token
        except Exception:
            logger.exception("LLM streaming failed during avatar generation")
            raise
