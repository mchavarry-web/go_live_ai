"""Correction-intent detection chain.

Wave B.1 (2026-05-06). When the user retracts, updates, or contradicts a
prior fact ("ya no me gusta el café", "cambié de trabajo", "olvida lo
que dije sobre X"), this chain produces a structured retraction signal
that the post-turn pipeline uses to mark matching insights as
``superseded`` so they stop surfacing in retrieval.

The chain DOES NOT decide which rows to flip — that's a vector-search
problem handled by the service layer. It only extracts the *intent*: a
short phrase describing what the user is correcting plus an optional
new value.
"""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic output ─────────────────────────────────────────────────────


class CorrectionSignal(BaseModel):
    """One retraction the user has expressed in this turn.

    Attributes:
        target_phrase: Short Spanish phrase describing what the user is
            retracting. Used as a query for semantic search against
            existing insights to find which rows to supersede.
        replacement: Optional new fact the user is asserting in place of
            the old one. When set, the service layer also stores this as
            a fresh insight.
        category_hint: Optional InsightCategory the retraction is in. Helps
            scope the supersede search.
        confidence: 0.0–1.0; conservative — only retract when the user is
            being explicit.
    """

    target_phrase: str = Field(..., max_length=200)
    replacement: str | None = Field(default=None, max_length=200)
    category_hint: str | None = Field(default=None)
    confidence: float = Field(..., ge=0.0, le=1.0)


class CorrectionSignals(BaseModel):
    """Wrapper for the LCEL parser. Empty list = no correction this turn."""

    corrections: list[CorrectionSignal] = Field(default_factory=list)


# ── Prompt ──────────────────────────────────────────────────────────────


_CORRECTION_TEMPLATE = """Sos un detector de retractaciones para un avatar digital con memoria.
Tu tarea: leer el mensaje del usuario y decidir si retracta, contradice o actualiza un hecho previo sobre si mismo.

QUE CUENTA COMO RETRACTACION (devolver con confianza 0.7+):
- "ya no me gusta X"
- "ya no trabajo en X"
- "olvida lo que te dije sobre X"
- "no, en realidad..."
- "cambie de Y" / "ya no Y"
- "eso ya no es asi"
- "me equivoque cuando dije que..."
- contradiccion explicita de algo conocido

QUE NO CUENTA (devolver lista vacia):
- preferencias nuevas que no contradicen nada anterior
- estado emocional momentaneo ("hoy estoy mal")
- preguntas, opiniones, hipoteticos
- cambios de tema sin retractacion

PARA CADA RETRACTACION:
- target_phrase: descripcion corta de lo que se retracta (ej "le gusta el cafe", "trabaja en X")
- replacement: opcional, el nuevo valor (ej "le gusta el te", "trabaja en Y")
- category_hint: una de personal_history, preference, relationship, goal, emotion, health, o null
- confidence: 0.7-1.0 para retractaciones explicitas, 0.5-0.7 para implicitas. NO retractes con confianza menor a 0.7 si tenes dudas.

Maximo 3 retractaciones por turno. Si no hay retractacion clara, devuelve lista vacia.

MENSAJE DEL USUARIO:
{user_message}

{format_instructions}"""


# ── Chain class ─────────────────────────────────────────────────────────


class CorrectionDetectorChain:
    """LCEL chain that classifies retraction/correction intent."""

    def __init__(self, llm: BaseChatModel, min_confidence: float = 0.7) -> None:
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=CorrectionSignals)
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", _CORRECTION_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="detect_corrections", run_type="chain")
    async def detect(self, user_message: str) -> list[CorrectionSignal]:
        """Return correction signals at or above ``min_confidence``.

        Failures yield an empty list — corrections are best-effort; the
        chat experience must never break because retraction detection
        timed out.
        """
        if not user_message or not user_message.strip():
            return []
        try:
            result: CorrectionSignals = await self.chain.ainvoke(
                {
                    "user_message": user_message,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )
        except Exception:
            logger.exception("Correction detection failed — skipping")
            return []
        return [
            sig
            for sig in result.corrections
            if sig.confidence >= self.min_confidence and sig.target_phrase.strip()
        ]
