"""Twitter/X content chain — pulls personality + opinion insights from
the user's tweets and replies."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TweetInsight(BaseModel):
    category: str = Field(
        ..., description="opinion, interest, values, emotion, relationship, goal"
    )
    content: str = Field(..., max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = Field(default="")


class TweetInsightList(BaseModel):
    insights: list[TweetInsight] = Field(default_factory=list)


_TWITTER_CONTENT_PROMPT = """\
Analiza la actividad de Twitter/X del usuario (tweets y replies propios,
sin retweets) para extraer opiniones claras, intereses, valores, y
patrones emocionales.

Datos:
{payload}

Devuelve entre 0 y 10 insights de alta confianza (>=0.7). Preferí
señales sobre valores y opiniones sostenidas por encima de reacciones
puntuales.

{format_instructions}
"""


class TwitterContentChain:
    def __init__(self, llm: BaseChatModel) -> None:
        self._parser = PydanticOutputParser(pydantic_object=TweetInsightList)
        prompt = ChatPromptTemplate.from_template(
            _TWITTER_CONTENT_PROMPT,
            partial_variables={"format_instructions": self._parser.get_format_instructions()},
        )
        self._chain = prompt | llm | self._parser

    @traceable(name="twitter_content_chain.extract")
    async def extract(self, payload: dict[str, object]) -> TweetInsightList:
        return await self._chain.ainvoke({"payload": payload})
