"""Social media insight extraction chain using LangChain.

Specialized chain for analyzing social media data (tweets, posts, bios)
in batch. Unlike InsightExtractionChain which processes single messages,
this chain receives a user's full social media footprint and synthesizes
high-level insights about personality, interests, and behavior patterns.
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


class SocialInsight(BaseModel):
    """A single insight extracted from social media analysis."""

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
    evidence: str = Field(
        default="",
        description=(
            "Breve referencia a la evidencia que respalda el insight "
            "(ej: 'Mencionado en bio y 3 tweets sobre tecnologia')."
        ),
    )


class SocialInsights(BaseModel):
    """Collection of insights extracted from social media data."""

    insights: list[SocialInsight] = Field(
        default_factory=list,
        description="Lista de insights extraidos del analisis de redes sociales.",
    )
    summary: str = Field(
        default="",
        description="Resumen breve (1-2 oraciones) del perfil digital del usuario.",
    )


# ── Extraction prompt ────────────────────────────────────────────────────

SOCIAL_INSIGHT_TEMPLATE = """Eres un analista de huella digital especializado en redes sociales.
Tu tarea es analizar el perfil y publicaciones de un usuario de {platform} para extraer
insights sobre su personalidad, intereses y comportamiento.

PERFIL DEL USUARIO:
- Username: {username}
- Bio: {bio}
- Miembro desde: {member_since}

PUBLICACIONES ({post_count} posts analizados):
{posts_text}

CATEGORIAS DISPONIBLES:
- personal_history: Historia personal, eventos de vida, experiencias pasadas.
- preference: Gustos, preferencias, cosas favoritas, intereses tematicos.
- relationship: Relaciones interpersonales, familia, amigos, comunidades.
- goal: Metas, objetivos, planes futuros, aspiraciones.
- emotion: Estados emocionales, sentimientos recurrentes, actitud general.
- health: Estado de salud, habitos de ejercicio, alimentacion.

REGLAS DE ANALISIS:
1. Analiza PATRONES a traves de multiples publicaciones, no post por post.
2. Filtra ruido: ignora retweets/reposts sin contexto propio, links solos, spam.
3. Los retweets/reposts indican afinidad pero con MENOR confianza (0.3-0.5) que
   contenido original (0.6-0.9).
4. La bio es una autodescripcion: tiene ALTA confianza (0.7-0.9).
5. Detecta intereses recurrentes (temas que aparecen en 2+ publicaciones).
6. Infiere rasgos de personalidad del tono, estilo y contenido.
7. Cada insight debe ser una oracion concisa (maximo 200 caracteres).
8. Incluye evidencia breve para cada insight.
9. Si no hay suficiente informacion para un insight, NO lo incluyas.
10. Genera un resumen de 1-2 oraciones del perfil digital.

{format_instructions}"""


# ── Chain class ──────────────────────────────────────────────────────────


class SocialMediaInsightChain:
    """LangChain chain for extracting insights from social media data in batch.

    Unlike InsightExtractionChain (conversational, one message at a time),
    this chain receives a user's full social media footprint and synthesizes
    patterns across multiple posts to produce high-level insights.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        min_confidence: float = 0.3,
    ) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=SocialInsights)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SOCIAL_INSIGHT_TEMPLATE),
            ]
        )

        self.chain = self.prompt | self.llm | self.parser

    def _format_posts(self, posts: list[dict]) -> str:
        """Format posts into a readable text block for the prompt."""
        if not posts:
            return "(Sin publicaciones disponibles)"

        lines: list[str] = []
        for i, post in enumerate(posts, 1):
            prefix = "[REPOST] " if post.get("is_repost") else ""
            date = post.get("date", "")
            date_str = f" ({date})" if date else ""
            media = post.get("media_types", [])
            media_str = f" [Media: {', '.join(media)}]" if media else ""
            lines.append(f"{i}. {prefix}{post['text']}{date_str}{media_str}")

        return "\n".join(lines)

    @traceable(name="extract_social_insights", run_type="chain")
    async def extract(
        self,
        platform: str,
        username: str,
        bio: str = "",
        member_since: str = "",
        posts: list[dict] | None = None,
    ) -> SocialInsights:
        """Extract insights from a user's social media data.

        Args:
            platform: Social media platform name (e.g. "Twitter").
            username: The user's handle on the platform.
            bio: The user's profile description.
            member_since: When the user joined the platform.
            posts: List of dicts with keys: text, is_repost, date, media_types.

        Returns:
            SocialInsights with extracted insights and summary.
        """
        posts = posts or []
        posts_text = self._format_posts(posts)
        original_count = sum(1 for p in posts if not p.get("is_repost"))
        repost_count = len(posts) - original_count

        try:
            result: SocialInsights = await self.chain.ainvoke(
                {
                    "platform": platform,
                    "username": username,
                    "bio": bio if bio else "(Sin bio)",
                    "member_since": member_since if member_since else "Desconocido",
                    "post_count": f"{len(posts)} total, {original_count} originales, {repost_count} reposts",
                    "posts_text": posts_text,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )

            valid_categories = {cat.value for cat in InsightCategory}
            validated_insights = [
                insight
                for insight in result.insights
                if insight.confidence >= self.min_confidence
                and insight.category in valid_categories
            ]

            logger.info(
                "Extracted %d social insights (%d after filtering) from %s/@%s",
                len(result.insights),
                len(validated_insights),
                platform,
                username,
            )

            return SocialInsights(
                insights=validated_insights,
                summary=result.summary,
            )

        except Exception:
            logger.exception(
                "Social insight extraction failed for %s/@%s",
                platform,
                username,
            )
            return SocialInsights(insights=[], summary="")
