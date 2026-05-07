"""Conversation summarization chain.

Produces a rolling, third-person summary of a conversation arc. The chain
runs every N turns (per ``ChatService._run_post_turn_tasks``) and accepts
an optional prior summary to integrate so the new row covers the whole
conversation history rather than re-summarizing from scratch.

The output is short (max 800 chars) — long enough to capture facts the
user shared and the avatar's response posture, brief enough that
swapping it in for an old message tail is a clear token win.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic output ─────────────────────────────────────────────────────


class ConversationSummary(BaseModel):
    """Structured output for ``ConversationSummaryChain``.

    Attributes:
        summary: Third-person Spanish summary, ≤ 800 chars.
        key_topics: 3-5 short topic tags (lowercased).
        token_count_estimate: Rough estimate of the summary's token cost,
            used by the read side to budget history-tail truncation.
    """

    summary: str = Field(..., max_length=800)
    key_topics: list[str] = Field(default_factory=list, max_length=8)
    token_count_estimate: int = Field(default=0, ge=0)


# ── Prompt ──────────────────────────────────────────────────────────────


CONVERSATION_SUMMARY_TEMPLATE = """Sos un compresor de conversaciones para un avatar digital personalizado.
Tu tarea es producir un resumen breve, en tercera persona neutral, de lo que se discutió.

USUARIO: {display_name}

REGLAS:
1. Máximo 800 caracteres.
2. Tercera persona neutral ("la usuaria mencionó", "el usuario contó"). NO uses primera ni segunda persona.
3. Si hay un resumen previo, INTEGRALO — no lo dupliqués. Tu salida debe cubrir TODO el arco hasta ahora.
4. Capturá: hechos personales que la usuaria compartió, decisiones tomadas, estado emocional dominante, peticiones pendientes.
5. Listá 3-5 temas clave como tags cortos (ej: "trabajo", "salud", "viaje a lima").
6. Estimá el conteo de tokens del resumen (aproximación: chars / 4).

RESUMEN PREVIO (puede estar vacío):
{prior_summary}

CONVERSACIÓN A RESUMIR:
{conversation_text}

{format_instructions}"""


# ── Chain class ─────────────────────────────────────────────────────────


class ConversationSummaryChain:
    """LCEL chain that produces a ``ConversationSummary`` from history.

    Usage::

        chain = ConversationSummaryChain(llm=llm)
        result = await chain.summarize(
            conversation_history=history,
            prior_summary=prior or "",
            display_name=user.display_name,
        )

    Errors are not swallowed — callers (``ConversationSummaryService``)
    decide what to do with a failed summarization.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=ConversationSummary)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", CONVERSATION_SUMMARY_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="summarize_conversation", run_type="chain")
    async def summarize(
        self,
        *,
        conversation_history: list[dict[str, str]],
        prior_summary: str = "",
        display_name: str = "el usuario",
    ) -> ConversationSummary:
        """Produce a summary covering ``prior_summary`` + ``conversation_history``.

        Args:
            conversation_history: List of ``{role, content}`` dicts.
            prior_summary: Existing summary text to integrate. Empty for
                first summarization of a conversation.
            display_name: User's display name for the prompt.

        Returns:
            A ``ConversationSummary`` instance.
        """
        conversation_text = "\n".join(
            f"{entry.get('role', 'user').upper()}: {entry.get('content', '')}"
            for entry in conversation_history
        ) or "(sin mensajes)"

        result: ConversationSummary = await self.chain.ainvoke(
            {
                "display_name": display_name,
                "prior_summary": prior_summary or "(sin resumen previo)",
                "conversation_text": conversation_text,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )
        return result
