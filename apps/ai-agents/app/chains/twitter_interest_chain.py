"""Twitter interest clustering — distills topical interests from the
user's likes + follows + replies.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Interest(BaseModel):
    topic: str = Field(..., description="tema en español, corto y específico")
    weight: float = Field(..., ge=0.0, le=1.0)
    evidence_count: int = Field(default=1, ge=0)


class TwitterInterests(BaseModel):
    interests: list[Interest] = Field(default_factory=list)


_TWITTER_INTEREST_PROMPT = """\
Dado un corpus de likes, follows y replies en Twitter/X, extrae los temas
de interés sostenidos del usuario. Un tema cuenta solo si aparece en
>=3 evidencias independientes.

Datos:
{payload}

Devuelve entre 0 y 15 intereses ordenados por peso (mayor primero).

{format_instructions}
"""


class TwitterInterestChain:
    def __init__(self, llm: BaseChatModel) -> None:
        self._parser = PydanticOutputParser(pydantic_object=TwitterInterests)
        prompt = ChatPromptTemplate.from_template(
            _TWITTER_INTEREST_PROMPT,
            partial_variables={"format_instructions": self._parser.get_format_instructions()},
        )
        self._chain = prompt | llm | self._parser

    @traceable(name="twitter_interest_chain.extract")
    async def extract(self, payload: dict[str, object]) -> TwitterInterests:
        return await self._chain.ainvoke({"payload": payload})
