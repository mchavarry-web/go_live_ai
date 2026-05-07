"""Search-engagement chain (Phase 15).

After a turn that involved a web search, capture whether the user's
*next* message engages with the searched topic and, if so, derive a
preference insight. Conservative confidence floor — search activity
alone is not enough; we need a follow-up signal from the user.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic output ─────────────────────────────────────────────────────


class EngagementSignal(BaseModel):
    """Structured output of ``SearchEngagementChain``.

    Attributes:
        is_engaged: True only when the user's follow-up shows clear
            interest (asks more, expresses enthusiasm, picks the topic
            up themselves). Polite acknowledgements ("ok", "interesante")
            are not engagement.
        derived_preference: A short Spanish preference statement to
            persist as an insight, or None when ``is_engaged`` is False.
        confidence: 0.0-1.0; the chain is encouraged to be conservative
            (most messages should land in the 0.5-0.7 band).
    """

    is_engaged: bool
    derived_preference: str | None = Field(default=None, max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


# ── Prompt ──────────────────────────────────────────────────────────────


SEARCH_ENGAGEMENT_TEMPLATE = """Sos un clasificador de engagement para un avatar digital.
En el turno anterior el avatar realizó una búsqueda web sobre un tema. Ahora tenemos
la respuesta del usuario al siguiente turno. Decidí si el usuario muestra interés
genuino en el tema (preguntas de seguimiento, entusiasmo, profundización).

REGLAS:
1. NO es engagement si el usuario solo dice "ok", "interesante", "ah", "gracias", "ya".
2. SÍ es engagement si pregunta más, comparte experiencia propia, pide detalles, o cambia el tema dentro del mismo área.
3. Si hay engagement, escribí una preferencia corta en tercera persona (≤ 200 chars), tipo "le interesa la programación cuántica".
4. Sé conservador: la mayoría de los turnos no califican.

QUERY DE BÚSQUEDA: {search_query}

RESUMEN DE LO ENCONTRADO (puede estar vacío):
{search_summary}

MENSAJE DE SEGUIMIENTO DEL USUARIO:
{user_followup_message}

{format_instructions}"""


# ── Chain class ─────────────────────────────────────────────────────────


class SearchEngagementChain:
    """LCEL chain that classifies user engagement with a recent web search."""

    def __init__(self, llm: BaseChatModel, min_confidence: float = 0.7) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=EngagementSignal)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SEARCH_ENGAGEMENT_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="search_engagement", run_type="chain")
    async def classify(
        self,
        *,
        search_query: str,
        search_summary: str,
        user_followup_message: str,
    ) -> EngagementSignal:
        """Run the chain. Caller is responsible for confidence-floor filtering."""
        result: EngagementSignal = await self.chain.ainvoke(
            {
                "search_query": search_query,
                "search_summary": search_summary or "(sin resumen)",
                "user_followup_message": user_followup_message,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )
        return result
