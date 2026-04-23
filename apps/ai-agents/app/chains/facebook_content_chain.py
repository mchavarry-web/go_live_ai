"""Facebook content analysis chain.

Analyses the user's Facebook footprint (profile, posts, reactions, about
fields) to pull personality + preference + relationship insights. Similar
shape to the Instagram chain but weighted toward "about me"-style fields
that FB exposes more liberally than IG.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FacebookInsight(BaseModel):
    category: str = Field(
        ...,
        description=(
            "Categoría: personal_history, preference, relationship, goal, "
            "emotion, health, values"
        ),
    )
    content: str = Field(..., max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = Field(default="")


class FacebookInsightList(BaseModel):
    insights: list[FacebookInsight] = Field(default_factory=list)


_FACEBOOK_CONTENT_PROMPT = """\
Eres un analista que extrae rasgos de personalidad, preferencias y vínculos
de la actividad de Facebook de un usuario.

Datos del usuario:
{payload}

Devuelve entre 0 y 10 insights de alta confianza (>=0.7). Evita insights
obvios o genéricos. Ignora contenido compartido sin comentario propio
(re-shares sin texto) porque no es alta señal.

{format_instructions}
"""


class FacebookContentChain:
    """LCEL chain: ChatPromptTemplate | llm | PydanticOutputParser."""

    def __init__(self, llm: BaseChatModel) -> None:
        self._parser = PydanticOutputParser(pydantic_object=FacebookInsightList)
        prompt = ChatPromptTemplate.from_template(
            _FACEBOOK_CONTENT_PROMPT,
            partial_variables={"format_instructions": self._parser.get_format_instructions()},
        )
        self._chain = prompt | llm | self._parser

    @traceable(name="facebook_content_chain.extract")
    async def extract(self, payload: dict[str, object]) -> FacebookInsightList:
        return await self._chain.ainvoke({"payload": payload})
