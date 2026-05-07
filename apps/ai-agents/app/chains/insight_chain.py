"""Insight extraction chain using LangChain.

Analyzes user messages and extracts structured insights using
PydanticOutputParser. Each insight includes a category, content,
and confidence score. All invocations are traced via LangSmith.
"""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.models.enums import InsightCategory

logger = logging.getLogger(__name__)


# ── Pydantic models for structured output ────────────────────────────────


class ExtractedInsight(BaseModel):
    """A single insight extracted from a user message.

    Attributes:
        category: The insight category.
        content: The insight content in natural language.
        confidence: Confidence score for this extraction (0.0-1.0).
    """

    category: str = Field(
        ...,
        description=(
            "Categoria del insight. Debe ser una de: "
            "personal_history, preference, relationship, goal, emotion, health"
        ),
    )
    content: str = Field(
        ...,
        description="Contenido del insight en lenguaje natural, maximo 200 caracteres.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza de la extraccion (0.0 a 1.0).",
    )


class ExtractedInsights(BaseModel):
    """Collection of insights extracted from a user message.

    Attributes:
        insights: List of extracted insights (may be empty).
    """

    insights: list[ExtractedInsight] = Field(
        default_factory=list,
        description="Lista de insights extraidos del mensaje. Puede estar vacia si no hay insights relevantes.",
    )


# ── Extraction prompt ────────────────────────────────────────────────────

INSIGHT_EXTRACTION_TEMPLATE = """Eres un analista de conversaciones para un avatar digital personalizado.
Tu tarea es extraer insights (conocimientos) sobre el usuario a partir del turno de conversacion.

CATEGORIAS DISPONIBLES:
- personal_history: Historia personal, eventos de vida, experiencias pasadas.
- preference: Gustos, preferencias, cosas favoritas.
- relationship: Relaciones interpersonales, familia, amigos.
- goal: Metas, objetivos, planes futuros.
- emotion: Estados emocionales, sentimientos recurrentes.
- health: Estado de salud, habitos de ejercicio, alimentacion.

REGLAS:
1. Extrae insights basados en lo que el USUARIO dijo — lo que afirmo, confirmo o reacciono.
2. Podés inferir insights de la respuesta del asistente SI el usuario la confirmo o no la contradijo.
3. NO inventes ni supongas informacion que el usuario no haya expresado o validado.
4. Cada insight debe ser una oracion corta y concisa (maximo 200 caracteres).
5. Asigna un nivel de confianza realista (0.5-1.0 para menciones explicitas, 0.3-0.5 para implicitas).
6. Si el turno no contiene informacion personal relevante, devuelve una lista vacia.
7. Ignora saludos, mensajes triviales o preguntas sin contenido personal.

CONTEXTO PREVIO SOBRE EL USUARIO:
{context}

TURNO DE CONVERSACION:
Usuario: {message}
{assistant_turn}

{format_instructions}"""


# ── Chain class ──────────────────────────────────────────────────────────


class InsightExtractionChain:
    """LangChain chain for extracting structured insights from user messages.

    Uses PydanticOutputParser to produce validated, typed insight objects
    from LLM analysis of user messages.

    Attributes:
        llm: The LangChain chat model for extraction.
        parser: Pydantic output parser for structured results.
        prompt: The ChatPromptTemplate for insight extraction.
        chain: The composed LCEL chain.
        min_confidence: Minimum confidence threshold for accepting insights
            (used as a fallback when ``category_min_confidence`` lacks a key).
        category_min_confidence: Per-category overrides. Sensitive categories
            (health/relationship/emotion) get a higher bar than the default;
            all other categories fall back to ``min_confidence``.
    """

    # Wave B.2 (2026-05-06) — sensitive categories get a stricter floor
    # because false positives there are higher-impact (a wrong "health"
    # insight can show up as "user takes medication X" — embarrassing).
    # action_usable bucket reserved for Wave C autonomy work; not active
    # in any current chain caller.
    _DEFAULT_BASE_CONFIDENCE = 0.55
    _DEFAULT_CATEGORY_CONFIDENCE: dict[str, float] = {
        "health": 0.65,
        "relationship": 0.65,
        "emotion": 0.65,
    }

    def __init__(
        self,
        llm: BaseChatModel,
        min_confidence: float | None = None,
        category_min_confidence: dict[str, float] | None = None,
    ) -> None:
        """Initialize the insight extraction chain.

        Args:
            llm: A LangChain BaseChatModel instance.
            min_confidence: Default confidence floor when a category has
                no explicit override. Defaults to 0.55 (Wave B.2). Pass
                an explicit value (e.g. 0.4 for legacy callers) to opt out.
            category_min_confidence: Optional per-category override map.
                Defaults to {health: 0.65, relationship: 0.65, emotion: 0.65}.
        """
        self.llm = llm
        self.min_confidence = (
            min_confidence
            if min_confidence is not None
            else self._DEFAULT_BASE_CONFIDENCE
        )
        if category_min_confidence is None:
            category_min_confidence = dict(self._DEFAULT_CATEGORY_CONFIDENCE)
        self.category_min_confidence = category_min_confidence
        self.parser = PydanticOutputParser(pydantic_object=ExtractedInsights)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", INSIGHT_EXTRACTION_TEMPLATE),
            ]
        )

        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="extract_insights", run_type="chain")
    async def extract(
        self,
        message: str,
        context: str = "",
        assistant_response: Optional[str] = None,
    ) -> list[ExtractedInsight]:
        """Extract insights from a conversation turn (user message + optional assistant reply).

        Args:
            message: The user's message text.
            context: Optional prior context about the user.
            assistant_response: The assistant's reply for this turn, used to
                capture confirmations or agreements the user did not contradict.

        Returns:
            List of ExtractedInsight objects above the confidence threshold.
        """
        assistant_turn = (
            f"Asistente: {assistant_response}" if assistant_response else ""
        )
        try:
            result: ExtractedInsights = await self.chain.ainvoke(
                {
                    "message": message,
                    "context": context if context else "No hay contexto previo.",
                    "assistant_turn": assistant_turn,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )

            # Filter by per-category minimum confidence (Wave B.2). Sensitive
            # categories (health/relationship/emotion) require a higher floor
            # than the base default. Unknown categories fall back to the base.
            def _floor_for(category: str) -> float:
                return self.category_min_confidence.get(category, self.min_confidence)

            filtered = [
                insight
                for insight in result.insights
                if insight.confidence >= _floor_for(insight.category)
            ]

            # Validate categories — avatar_evolution is reserved for PersonaEvolutionChain
            user_categories = {
                cat.value
                for cat in InsightCategory
                if cat != InsightCategory.AVATAR_EVOLUTION
            }
            validated = [
                insight
                for insight in filtered
                if insight.category in user_categories
            ]

            logger.info(
                "Extracted %d insights (%d after filtering) from message",
                len(result.insights),
                len(validated),
            )

            return validated

        except Exception:
            logger.exception("Insight extraction failed")
            # Return empty list on failure — don't break the chat flow
            return []
