"""Event extraction chain.

Extracts dated commitments (appointments, deadlines, scheduled
activities) from a chat turn and resolves relative phrases like
"mañana" or "el martes a las 3" into absolute UTC timestamps.

Hybrid resolution: the LLM produces an ISO 8601 string anchored on
the user's local timezone, then ``dateparser`` independently parses
the raw fragment. We accept the LLM's value when both agree within
2 days; otherwise prefer ``dateparser`` (more conservative on
underspecified phrases). Events with neither source resolving, or
landing outside ``[now - 1h, now + 365d]``, are dropped.

Outputs a list of ``ResolvedEvent`` dataclasses with absolute UTC
timestamps, ready for ``EventRepository.create_event``.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import dateparser
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic models for structured LLM output ───────────────────────────


class ExtractedEvent(BaseModel):
    """A single dated event the LLM extracted from the turn.

    Attributes:
        title: Short label for the event (max 200 chars).
        occurs_at_iso: ISO 8601 datetime in the user's local timezone, e.g.
            ``"2026-05-12T15:00:00-05:00"``. When the user gave no clock,
            the time component is ``00:00:00`` and ``has_explicit_time``
            is False.
        has_explicit_time: True if the user named a clock time.
        raw_text: Verbatim fragment of the user message that mentions the
            event. Used as the dateparser input and stored for audit.
        confidence: Extraction confidence score (0.0-1.0).
    """

    title: str = Field(..., max_length=200)
    occurs_at_iso: str = Field(
        ...,
        description=(
            "ISO 8601 datetime in la zona horaria local del usuario. "
            "Ejemplo: '2026-05-12T15:00:00-05:00'. Si el usuario no dio hora, "
            "usa 00:00:00 y has_explicit_time=false."
        ),
    )
    has_explicit_time: bool = Field(
        ...,
        description="True si el usuario mencionó una hora explícita.",
    )
    raw_text: str = Field(
        ...,
        max_length=500,
        description="Fragmento literal del mensaje que menciona el evento.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedEvents(BaseModel):
    """Collection wrapper for the LCEL parser."""

    events: list[ExtractedEvent] = Field(default_factory=list)


# ── Internal post-resolution dataclass ──────────────────────────────────


@dataclass(frozen=True)
class ResolvedEvent:
    """An extracted event with its UTC timestamp resolved and validated.

    Attributes:
        title: Short label.
        occurs_at: Absolute tz-aware UTC datetime.
        occurs_at_has_time: False when only a date was given.
        raw_text: Verbatim fragment.
        confidence: Extraction confidence.
    """

    title: str
    occurs_at: datetime
    occurs_at_has_time: bool
    raw_text: str
    confidence: float


# ── Prompt ──────────────────────────────────────────────────────────────


EVENT_EXTRACTION_TEMPLATE = """Eres un extractor de eventos y compromisos con fecha para un avatar digital personalizado.
Tu tarea es identificar eventos futuros (citas, reuniones, vuelos, deadlines, llamadas, eventos sociales) que el usuario mencionó o confirmó en el turno de conversacion.

ANCLAS TEMPORALES (CRITICAS — usalas para resolver frases relativas):
FECHA Y HORA ACTUAL (UTC): {now_utc}
ZONA HORARIA DEL USUARIO: {timezone}
FECHA Y HORA DEL MENSAJE (UTC): {message_created_at}

DEFINICION DE EVENTO:
Un evento es algo que el usuario dijo o confirmó que va a hacer en una fecha o momento específico.
Ejemplos:
- "Tengo dentista el martes a las 3" → evento.
- "Voy a salir con María mañana" → evento.
- "Tengo vuelo a Lima el 15" → evento.
- "Reunión de trabajo el viernes a las 10am" → evento.

QUE IGNORAR:
- Hipotéticos: "si voy al dentista...", "tal vez vaya a..."
- Eventos pasados: "ayer fui al doctor", "la semana pasada vi a María"
- Intenciones recurrentes sin fecha: "voy a empezar a hacer ejercicio", "algún día quiero viajar a Japón"
- Saludos o mensajes triviales sin contenido temporal específico.

REGLAS DE RESOLUCION DE FECHA:
1. Resuelve frases relativas ("mañana", "el martes", "en 2 semanas") usando las anclas temporales.
2. Devuelve la fecha en formato ISO 8601 con offset de la zona horaria local del usuario.
3. Si el usuario no dio hora, usa 00:00:00 y marca has_explicit_time=false.
4. NO inventes fechas. Si no podés resolver una fecha con confianza, no incluyas el evento.
5. Asigna confianza alta (0.7+) cuando hay fecha y hora explícitas; media (0.5-0.7) cuando solo hay fecha; baja (<0.5) si la fecha es ambigua.

CONTEXTO PREVIO:
{context}

TURNO DE CONVERSACION:
Usuario: {message}
{assistant_turn}

{format_instructions}"""


# ── Chain class ─────────────────────────────────────────────────────────


class EventExtractionChain:
    """Extract dated commitments from a chat turn.

    The chain is invoked from ``ChatService._extract_and_store_events``
    after each chat turn (post-stream, non-blocking). Output is a list
    of ``ResolvedEvent`` instances ready for ``EventRepository``.

    Attributes:
        llm: LangChain chat model used for extraction.
        min_confidence: Minimum confidence to keep an event (default 0.6,
            higher than the 0.4 insight floor — events are higher-stakes).
        disagreement_days: Maximum allowed difference, in days, between
            the LLM-resolved timestamp and the dateparser-resolved
            timestamp. Beyond this we drop the event as ambiguous.
        future_horizon_days: Reject events further out than this from now.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        min_confidence: float = 0.6,
        disagreement_days: int = 2,
        future_horizon_days: int = 365,
    ) -> None:
        """Initialize the chain.

        Args:
            llm: A LangChain ``BaseChatModel`` instance.
            min_confidence: Minimum confidence floor (0.0-1.0).
            disagreement_days: LLM/dateparser tolerance window (days).
            future_horizon_days: Drop events occurring further than this.
        """
        self.llm = llm
        self.min_confidence = min_confidence
        self.disagreement_days = disagreement_days
        self.future_horizon_days = future_horizon_days
        self.parser = PydanticOutputParser(pydantic_object=ExtractedEvents)

        self.prompt = ChatPromptTemplate.from_messages(
            [("system", EVENT_EXTRACTION_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="extract_events", run_type="chain")
    async def extract(
        self,
        *,
        message: str,
        now_utc: datetime,
        timezone: str,
        message_created_at: datetime,
        context: str = "",
        assistant_response: str | None = None,
    ) -> list[ResolvedEvent]:
        """Extract and resolve events from a conversation turn.

        Args:
            message: The user's message text.
            now_utc: Current UTC timestamp; used as the ``RELATIVE_BASE``
                anchor (when ``message_created_at`` is unavailable).
            timezone: IANA timezone of the user (e.g. ``"America/Lima"``).
            message_created_at: When the user sent the message (UTC).
                Used as the dateparser ``RELATIVE_BASE`` so "mañana"
                resolves relative to the message, not extraction time.
            context: Optional prior context about the user.
            assistant_response: Optional assistant turn (for confirmation
                signals — same pattern as the insight chain).

        Returns:
            List of ``ResolvedEvent`` instances. Empty on extraction
            failure or when no events meet the confidence/window criteria.
        """
        assistant_turn = (
            f"Asistente: {assistant_response}" if assistant_response else ""
        )

        try:
            result: ExtractedEvents = await self.chain.ainvoke(
                {
                    "message": message,
                    "context": context if context else "Sin contexto previo.",
                    "assistant_turn": assistant_turn,
                    "now_utc": now_utc.isoformat(),
                    "timezone": timezone,
                    "message_created_at": message_created_at.isoformat(),
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )
        except Exception:
            logger.exception("Event extraction LLM call failed")
            return []

        resolved: list[ResolvedEvent] = []
        for ev in result.events:
            if ev.confidence < self.min_confidence:
                logger.debug(
                    "Dropping event below confidence floor: %r (%.2f < %.2f)",
                    ev.title,
                    ev.confidence,
                    self.min_confidence,
                )
                continue

            title = ev.title.strip()
            if not title:
                continue

            occurs_at = self._resolve_datetime(
                llm_iso=ev.occurs_at_iso,
                raw_text=ev.raw_text,
                user_tz=timezone,
                relative_base=message_created_at,
            )
            if occurs_at is None:
                logger.info(
                    "Dropping event %r: could not resolve a valid datetime",
                    title,
                )
                continue

            if not self._within_window(occurs_at, now_utc=now_utc):
                logger.info(
                    "Dropping event %r: occurs_at %s outside acceptance window",
                    title,
                    occurs_at.isoformat(),
                )
                continue

            resolved.append(
                ResolvedEvent(
                    title=title[:200],
                    occurs_at=occurs_at,
                    occurs_at_has_time=ev.has_explicit_time,
                    raw_text=ev.raw_text.strip()[:500],
                    confidence=ev.confidence,
                )
            )

        logger.info(
            "Event extraction yielded %d/%d resolved events",
            len(resolved),
            len(result.events),
        )
        return resolved

    # ── Internal helpers ────────────────────────────────────────────

    def _resolve_datetime(
        self,
        *,
        llm_iso: str,
        raw_text: str,
        user_tz: str,
        relative_base: datetime,
    ) -> datetime | None:
        """Resolve the event timestamp by combining LLM and dateparser output.

        Strategy:
        1. Parse the LLM's ISO string. If it has no tz, attach the user's tz.
        2. Re-parse ``raw_text`` with dateparser anchored on ``relative_base``.
        3. If both succeed and agree within ``disagreement_days`` → use the
           LLM's value (it tends to handle Spanish weekday phrasing better).
        4. If they disagree beyond the tolerance → drop the event entirely.
           Neither source is trustworthy in isolation when they conflict.
        5. If only one succeeds → use that one (the other was silent, not
           contradicting). LLM-only carries some hallucination risk; dateparser-
           only is conservative for explicit phrases like "tomorrow at 5".
        6. If neither succeeds → drop.

        All return values are tz-aware UTC datetimes.
        """
        llm_dt = self._parse_llm_iso(llm_iso, user_tz=user_tz)
        dp_dt = self._parse_with_dateparser(
            raw_text=raw_text,
            user_tz=user_tz,
            relative_base=relative_base,
        )

        if llm_dt is None and dp_dt is None:
            return None
        if llm_dt is None:
            return dp_dt
        if dp_dt is None:
            return llm_dt

        delta = abs(llm_dt - dp_dt)
        if delta <= timedelta(days=self.disagreement_days):
            return llm_dt
        logger.info(
            "LLM/dateparser disagreement %s > %d days for raw_text=%r — dropping event",
            delta,
            self.disagreement_days,
            raw_text,
        )
        return None

    @staticmethod
    def _parse_llm_iso(iso_str: str, *, user_tz: str) -> datetime | None:
        """Parse the LLM's ISO 8601 string, attaching user's tz if naive."""
        try:
            parsed = datetime.fromisoformat(iso_str.strip())
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is None:
            try:
                from zoneinfo import ZoneInfo

                parsed = parsed.replace(tzinfo=ZoneInfo(user_tz))
            except Exception:
                return None
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse_with_dateparser(
        *,
        raw_text: str,
        user_tz: str,
        relative_base: datetime,
    ) -> datetime | None:
        """Run dateparser on the raw fragment in Spanish + English."""
        try:
            settings: dict[str, Any] = {
                "RELATIVE_BASE": relative_base.astimezone(UTC).replace(tzinfo=None),
                "TIMEZONE": user_tz,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            }
            result = dateparser.parse(
                raw_text,
                languages=["es", "en"],
                settings=settings,
            )
        except Exception:
            logger.exception("dateparser failed on raw_text=%r", raw_text)
            return None
        if result is None:
            return None
        if result.tzinfo is None:
            try:
                from zoneinfo import ZoneInfo

                result = result.replace(tzinfo=ZoneInfo(user_tz))
            except Exception:
                return None
        return result.astimezone(UTC)

    def _within_window(self, occurs_at: datetime, *, now_utc: datetime) -> bool:
        """Check the resolved timestamp falls in ``[now - 1h, now + horizon]``.

        The 1-hour past tolerance allows for tiny clock skew without
        rejecting events the user just confirmed for the next 5 minutes.
        """
        floor = now_utc - timedelta(hours=1)
        ceiling = now_utc + timedelta(days=self.future_horizon_days)
        return floor <= occurs_at <= ceiling
