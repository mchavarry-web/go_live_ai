"""Slang calibrator chain using LangChain.

Analyzes recent user messages to determine their actual formality level
and detect custom expressions not present in the dialect catalog. Runs
post-turn (non-blocking) to refine the language style profile over time.

The detected formality and expressions are stored as ``language_style``
insights and later injected into the system prompt via the language
style section builder.
"""

import json
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SlangProfile(BaseModel):
    """Detected language style profile from user messages.

    Attributes:
        formality_level: How formal the user writes (0.0 = very informal,
            1.0 = very formal).
        custom_expressions: Slang, idioms, or recurring expressions the
            user employs that may not be in the standard dialect catalog.
        emoji_frequency: How often the user uses emojis.
    """

    formality_level: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Nivel de formalidad del usuario (0.0=muy informal, 1.0=muy formal).",
    )
    custom_expressions: list[str] = Field(
        default_factory=list,
        description="Expresiones, jergas o modismos recurrentes del usuario que no son standard.",
    )
    emoji_frequency: str = Field(
        ...,
        description="Frecuencia de emojis: 'none', 'low', 'high'.",
    )


_CALIBRATOR_TEMPLATE = """Analiza los siguientes mensajes de un usuario y determina su estilo lingüístico.

NO estás detectando el dialecto (ya lo sabemos). Solo necesitas medir:
1. Qué tan formal o informal escribe (0.0 = muy informal con abreviaciones y jerga pesada, 1.0 = muy formal y cuidado).
2. Expresiones, jergas o muletillas recurrentes que usa y que son propias de esta persona (no las genéricas del dialecto).
3. Con qué frecuencia usa emojis: "none" si no usa, "low" si usa pocos, "high" si usa muchos.

MENSAJES DEL USUARIO (los más recientes):
{user_messages}

{format_instructions}"""


class SlangCalibratorChain:
    """Chain that calibrates formality level and custom expressions.

    Designed to run post-turn in parallel with insight extraction.
    Uses minimal tokens to keep cost low.

    Attributes:
        llm: The LangChain chat model for analysis.
        parser: Pydantic output parser for structured results.
        chain: The composed LCEL chain.
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=SlangProfile)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", _CALIBRATOR_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="calibrate_slang", run_type="chain")
    async def calibrate(
        self,
        user_messages: list[str],
    ) -> SlangProfile | None:
        """Analyze user messages and return a slang profile.

        Args:
            user_messages: Recent user messages (at least 2-3 for accuracy).

        Returns:
            A SlangProfile with formality level and custom expressions,
            or None if analysis fails or there are too few messages.
        """
        if len(user_messages) < 2:
            return None

        formatted_messages = "\n".join(
            f"- \"{msg}\"" for msg in user_messages[-10:]
        )

        try:
            result: SlangProfile = await self.chain.ainvoke(
                {
                    "user_messages": formatted_messages,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )
            logger.info(
                "Slang calibration: formality=%.2f, custom_expressions=%d, emoji=%s",
                result.formality_level,
                len(result.custom_expressions),
                result.emoji_frequency,
            )
            return result
        except Exception:
            logger.exception("Slang calibrator chain failed — skipping")
            return None

    @staticmethod
    def profile_to_insight_content(profile: SlangProfile) -> str:
        """Serialize a SlangProfile to a string for storage as insight content.

        Args:
            profile: The calibrated slang profile.

        Returns:
            JSON string suitable for insight storage.
        """
        return json.dumps(
            {
                "formality_level": profile.formality_level,
                "custom_expressions": profile.custom_expressions,
                "emoji_frequency": profile.emoji_frequency,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def parse_insight_content(content: str) -> tuple[float | None, list[str] | None]:
        """Deserialize language style insight content.

        Args:
            content: JSON string from a ``language_style`` insight.

        Returns:
            Tuple of (formality_level, custom_expressions). Both may be
            None if parsing fails.
        """
        try:
            data = json.loads(content)
            return (
                data.get("formality_level"),
                data.get("custom_expressions"),
            )
        except (json.JSONDecodeError, AttributeError):
            return None, None
