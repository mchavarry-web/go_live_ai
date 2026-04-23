"""Instagram interest mapping chain for topics and following analysis.

Analyzes recommended topics and followed accounts to infer user interests,
goals, and lifestyle preferences. Uses the LLM's knowledge of public
accounts to categorize and extract patterns.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.models.enums import InsightCategory

logger = logging.getLogger(__name__)


class InterestInsight(BaseModel):
    """A single insight from interest/following analysis."""

    category: str = Field(
        ...,
        description=(
            "Categoria del insight: personal_history, preference, "
            "relationship, goal, emotion, health"
        ),
    )
    content: str = Field(
        ...,
        description="Contenido del insight, maximo 200 caracteres.",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confianza de la extraccion (0.0 a 1.0).",
    )
    evidence: str = Field(
        default="",
        description="Referencia breve a la evidencia.",
    )


class InterestInsights(BaseModel):
    """Collection of insights from topics and following."""

    insights: list[InterestInsight] = Field(default_factory=list)
    summary: str = Field(default="")


INTEREST_TEMPLATE = """Eres un analista de intereses digitales especializado en Instagram.
Tu tarea es inferir los intereses, metas y preferencias de un usuario basandote en
los temas que Instagram le recomienda y las cuentas que sigue.

TEMAS RECOMENDADOS POR INSTAGRAM ({topic_count} temas):
{topics_text}

CUENTAS QUE SIGUE ({following_count} cuentas, se muestra una muestra representativa):
{following_text}

CATEGORIAS DISPONIBLES:
- personal_history: Historia personal, eventos, experiencias.
- preference: Gustos, preferencias, intereses tematicos.
- relationship: Comunidades, grupos de afinidad.
- goal: Metas, objetivos, aspiraciones (ej: sigue cuentas de coaching, fitness).
- emotion: Actitud general, tipo de contenido emocional que consume.
- health: Salud, nutricion, fitness, bienestar.

REGLAS:
1. Los TEMAS recomendados tienen confianza MEDIA-ALTA (0.5-0.7) porque Instagram
   los asigna basandose en el comportamiento real del usuario.
2. Las CUENTAS que sigue tienen confianza MEDIA (0.4-0.6) porque seguir no
   implica necesariamente interes activo.
3. Si reconoces cuentas publicas conocidas, usa ese conocimiento para inferir
   intereses (ej: @nike -> deporte, @natgeo -> naturaleza/viajes).
4. Busca PATRONES: si sigue muchas cuentas de un mismo tema, la confianza sube.
5. Agrupa intereses similares en un solo insight en lugar de uno por cuenta.
6. No generes insights sobre cuentas que no reconoces o son ambiguas.
7. Cada insight debe ser conciso (maximo 200 caracteres).

{format_instructions}"""


class InstagramInterestChain:
    """Extracts insights from Instagram topics and following lists."""

    def __init__(self, llm: BaseChatModel, min_confidence: float = 0.3) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=InterestInsights)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", INTEREST_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    def _format_topics(self, topics: list[str]) -> str:
        if not topics:
            return "(Sin temas disponibles)"
        return "\n".join(f"- {t}" for t in topics)

    def _format_following(self, following: list[str], max_sample: int = 200) -> str:
        if not following:
            return "(Sin cuentas disponibles)"
        sample = following[:max_sample]
        lines = [f"@{u}" for u in sample]
        result = ", ".join(lines)
        if len(following) > max_sample:
            result += f"\n... y {len(following) - max_sample} cuentas mas"
        return result

    @traceable(name="extract_instagram_interest_insights", run_type="chain")
    async def extract(
        self, topics: list[str], following: list[str],
    ) -> InterestInsights:
        if not topics and not following:
            return InterestInsights()

        try:
            result: InterestInsights = await self.chain.ainvoke({
                "topic_count": str(len(topics)),
                "topics_text": self._format_topics(topics),
                "following_count": str(len(following)),
                "following_text": self._format_following(following),
                "format_instructions": self.parser.get_format_instructions(),
            })

            valid_categories = {cat.value for cat in InsightCategory}
            validated = [
                ins for ins in result.insights
                if ins.confidence >= self.min_confidence
                and ins.category in valid_categories
            ]

            logger.info(
                "Instagram interests: %d insights (%d after filtering)",
                len(result.insights), len(validated),
            )
            return InterestInsights(insights=validated, summary=result.summary)

        except Exception:
            logger.exception("Instagram interest insight extraction failed")
            return InterestInsights()
