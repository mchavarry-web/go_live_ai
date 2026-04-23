"""Instagram content analysis chain for extracting insights from comments.

Analyzes user-generated comments on Instagram posts to extract personality
traits, interests, emotional patterns, and relationship indicators.
Comments are high-signal data since users actively chose to write them.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

from app.models.enums import InsightCategory

logger = logging.getLogger(__name__)


class ContentInsight(BaseModel):
    """A single insight extracted from Instagram comment analysis."""

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


class ContentInsights(BaseModel):
    """Collection of insights from Instagram comments."""

    insights: list[ContentInsight] = Field(default_factory=list)
    summary: str = Field(default="")


CONTENT_TEMPLATE = """Eres un analista de comportamiento digital especializado en Instagram.
Tu tarea es analizar los comentarios que un usuario ha escrito en publicaciones de Instagram
para extraer insights sobre su personalidad, intereses y relaciones.

COMENTARIOS DEL USUARIO ({comment_count} comentarios analizados):
{comments_text}

CATEGORIAS DISPONIBLES:
- personal_history: Historia personal, eventos de vida, experiencias.
- preference: Gustos, preferencias, intereses tematicos.
- relationship: Relaciones interpersonales, personas con las que interactua.
- goal: Metas, objetivos, aspiraciones.
- emotion: Tono emocional recurrente, actitud general.
- health: Salud, ejercicio, alimentacion.

REGLAS:
1. Los comentarios son contenido ORIGINAL del usuario: confianza alta (0.6-0.9).
2. Busca PATRONES: temas recurrentes, personas a las que comenta repetidamente.
3. El tono de los comentarios revela personalidad (entusiasta, critico, empatico, etc).
4. Si comenta frecuentemente a un mismo usuario, indica una relacion relevante.
5. Ignora comentarios genericos como emojis solos o "jajaja".
6. Cada insight debe ser conciso (maximo 200 caracteres).
7. Si hay pocos comentarios o son poco informativos, genera menos insights.

{format_instructions}"""


class InstagramContentChain:
    """Extracts insights from Instagram comments."""

    def __init__(self, llm: BaseChatModel, min_confidence: float = 0.4) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=ContentInsights)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", CONTENT_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    def _format_comments(self, comments: list[dict]) -> str:
        if not comments:
            return "(Sin comentarios disponibles)"

        lines: list[str] = []
        for i, c in enumerate(comments, 1):
            owner = c.get("post_owner", "")
            owner_str = f" [en post de @{owner}]" if owner else ""
            lines.append(f"{i}. \"{c['text']}\"{owner_str}")
        return "\n".join(lines)

    @traceable(name="extract_instagram_content_insights", run_type="chain")
    async def extract(self, comments: list[dict]) -> ContentInsights:
        if not comments:
            return ContentInsights()

        try:
            result: ContentInsights = await self.chain.ainvoke({
                "comment_count": str(len(comments)),
                "comments_text": self._format_comments(comments),
                "format_instructions": self.parser.get_format_instructions(),
            })

            valid_categories = {cat.value for cat in InsightCategory}
            validated = [
                ins for ins in result.insights
                if ins.confidence >= self.min_confidence
                and ins.category in valid_categories
            ]

            logger.info(
                "Instagram content: %d insights (%d after filtering)",
                len(result.insights), len(validated),
            )
            return ContentInsights(insights=validated, summary=result.summary)

        except Exception:
            logger.exception("Instagram content insight extraction failed")
            return ContentInsights()
