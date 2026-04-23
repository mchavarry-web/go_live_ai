"""Facebook social-graph chain — extracts relationship patterns from the
user's friends / groups / pages, looking for recurring ties, close circles,
and interest clusters.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SocialTie(BaseModel):
    name: str
    kind: str = Field(
        ..., description="close_friend | acquaintance | family | colleague | community"
    )
    evidence: str = Field(default="")
    confidence: float = Field(..., ge=0.0, le=1.0)


class FacebookSocialGraph(BaseModel):
    ties: list[SocialTie] = Field(default_factory=list)
    group_interests: list[str] = Field(default_factory=list)


_FACEBOOK_SOCIAL_PROMPT = """\
Eres un analista que infiere el círculo social de un usuario a partir de
sus grupos / páginas / amistades en Facebook:

Datos:
{payload}

Devuelve entre 0 y 15 vínculos de alta confianza, y hasta 10 intereses
agregados por grupos.

{format_instructions}
"""


class FacebookSocialChain:
    def __init__(self, llm: BaseChatModel) -> None:
        self._parser = PydanticOutputParser(pydantic_object=FacebookSocialGraph)
        prompt = ChatPromptTemplate.from_template(
            _FACEBOOK_SOCIAL_PROMPT,
            partial_variables={"format_instructions": self._parser.get_format_instructions()},
        )
        self._chain = prompt | llm | self._parser

    @traceable(name="facebook_social_chain.extract")
    async def extract(self, payload: dict[str, object]) -> FacebookSocialGraph:
        return await self._chain.ainvoke({"payload": payload})
