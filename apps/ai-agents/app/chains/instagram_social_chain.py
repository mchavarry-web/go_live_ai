"""Instagram social graph analysis chain.

Analyzes the user's close friends and blocked profiles to extract
insights about their social behavior, relationship patterns, and
emotional boundaries. This is inferential data with lower confidence.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.models.enums import InsightCategory

logger = logging.getLogger(__name__)


class SocialGraphInsight(BaseModel):
    """A single insight from social graph analysis."""

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


class SocialGraphInsights(BaseModel):
    """Collection of insights from social graph analysis."""

    insights: list[SocialGraphInsight] = Field(default_factory=list)
    summary: str = Field(default="")


SOCIAL_GRAPH_TEMPLATE = """Eres un psicologo social digital especializado en analizar
patrones de relaciones en redes sociales.

Tu tarea es analizar la estructura social de un usuario de Instagram basandote en
sus close friends y usuarios bloqueados para inferir rasgos de personalidad social.

DATOS DEL GRAFO SOCIAL:
- Total de cuentas que sigue: {following_count}
- Close friends: {close_friends_count} personas
- Usuarios bloqueados: {blocked_count} personas

CLOSE FRIENDS:
{close_friends_text}

USUARIOS BLOQUEADOS:
{blocked_text}

CATEGORIAS DISPONIBLES:
- personal_history: Historia personal, eventos, experiencias.
- preference: Gustos, preferencias en relaciones sociales.
- relationship: Patrones de relacion, tamano del circulo intimo, selectividad.
- goal: Metas sociales, tipo de comunidad que busca.
- emotion: Actitud social, apertura o reserva emocional.
- health: Bienestar social, manejo de relaciones toxicas.

REGLAS:
1. Confianza BAJA-MEDIA (0.3-0.5) porque estos datos son muy inferenciales.
2. El RATIO close friends / following indica selectividad social.
3. Un numero alto de bloqueados puede indicar limites saludables o conflictos.
4. Pocos close friends puede indicar introversion o selectividad.
5. NO hagas juicios negativos: interpreta de forma neutral o positiva.
6. Si los datos son muy escasos (0 close friends, 0 blocked), genera
   maximo 1-2 insights generales.
7. Cada insight debe ser conciso (maximo 200 caracteres).
8. No intentes identificar personas por sus usernames.

{format_instructions}"""


class InstagramSocialGraphChain:
    """Extracts insights from Instagram close friends and blocked users."""

    def __init__(self, llm: BaseChatModel, min_confidence: float = 0.3) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=SocialGraphInsights)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", SOCIAL_GRAPH_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="extract_instagram_social_graph_insights", run_type="chain")
    async def extract(
        self,
        close_friends: list[str],
        blocked: list[str],
        following_count: int = 0,
    ) -> SocialGraphInsights:
        if not close_friends and not blocked and following_count == 0:
            return SocialGraphInsights()

        close_text = (
            ", ".join(f"@{u}" for u in close_friends)
            if close_friends
            else "(Ninguno)"
        )
        blocked_text = (
            ", ".join(f"@{u}" for u in blocked)
            if blocked
            else "(Ninguno)"
        )

        try:
            result: SocialGraphInsights = await self.chain.ainvoke({
                "following_count": str(following_count),
                "close_friends_count": str(len(close_friends)),
                "blocked_count": str(len(blocked)),
                "close_friends_text": close_text,
                "blocked_text": blocked_text,
                "format_instructions": self.parser.get_format_instructions(),
            })

            valid_categories = {cat.value for cat in InsightCategory}
            validated = [
                ins for ins in result.insights
                if ins.confidence >= self.min_confidence
                and ins.category in valid_categories
            ]

            logger.info(
                "Instagram social graph: %d insights (%d after filtering)",
                len(result.insights), len(validated),
            )
            return SocialGraphInsights(insights=validated, summary=result.summary)

        except Exception:
            logger.exception("Instagram social graph insight extraction failed")
            return SocialGraphInsights()
