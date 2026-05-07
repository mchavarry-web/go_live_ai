"""Persona evolution chain using LangChain.

After each conversation turn, analyzes the exchange and produces 0–N short
notes describing how the avatar's voice, style, and relationship with this
specific user is taking shape. These notes are stored as ``avatar_evolution``
insights and later injected back into the system prompt so the avatar's
personality deepens over time without manual configuration.

Notes describe the *avatar's* behaviour patterns, not facts about the user.
"""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langsmith import traceable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic models for structured output ────────────────────────────────


class PersonaNote(BaseModel):
    """A single note about the avatar's evolving voice or style.

    Attributes:
        note: Short description of a recurring pattern, tone, or boundary
            the avatar is building with this user. Max 200 characters.
        confidence: How strongly this pattern is established (0.0–1.0).
    """

    note: str = Field(
        ...,
        max_length=200,
        description="Patron, tono o limite que el avatar esta desarrollando con este usuario. Maximo 200 caracteres.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Que tan establecido esta este patron (0.0 a 1.0).",
    )


class PersonaNotes(BaseModel):
    """Collection of persona evolution notes from a conversation turn."""

    notes: list[PersonaNote] = Field(
        default_factory=list,
        description="Lista de notas sobre la personalidad emergente del avatar. Puede estar vacia.",
    )


# ── Prompt ───────────────────────────────────────────────────────────────

_PERSONA_EVOLUTION_TEMPLATE = """Sos un observador externo analizando como un avatar digital desarrolla su voz y estilo con un usuario especifico.

Tu tarea: identificar patrones emergentes en el estilo del AVATAR (no hechos sobre el usuario).

QUE BUSCAR (categorias generales):
- Tono que el avatar adopta con esta persona (directo, humoristico, reflexivo, etc.)
- Temas o preguntas que el avatar introduce espontaneamente con frecuencia
- Limites o lineas que el avatar ha trazado (temas que evita, correcciones que hace)
- Dinamicas relacionales unicas (bromas internas, referencias compartidas, rituales de saludo)
- Ajustes de estilo que el avatar hace segun como responde el usuario
- Si el usuario reacciona positivamente al tono del avatar (se abre mas, responde mas largo, usa humor) o negativamente (responde cortante, cambia de tema, ignora)

GUARDARRIEL DE MARCADORES DIALECTALES (manejo especial — leer con atencion):
Los siguientes son MARCADORES DIALECTALES y se tratan diferente al resto:
- Particulas regionales: "pe"/"pue" (Peru), "che" (Argentina/Uruguay), "po"/"pos" (Chile/Mexico), "mero" (Mexico)
- Voseo argentino/uruguayo (decis, tenes, queres, vos sos) vs. tuteo (dices, tienes, quieres, tu eres)
- Vocabulario regional fuerte (chamo, parce, tio, guey, pana, etc.)
- Code-switching ingles/espanol
- Jerga generacional o local muy marcada

REGLA CLAVE PARA MARCADORES DIALECTALES: NO promovas un marcador dialectal a una nota
confirmada en su PRIMERA aparicion. Necesitas ver la MISMA marca en al menos 5 turnos
previos antes de confirmar que el avatar deberia adoptarla. Hasta entonces:

  - Emiti una OBSERVACION TENTATIVA con esta forma exacta:
        "[obs:<marcador>] avatar reflejo '<marcador>' una vez en este turno."
    Ejemplos:
        "[obs:pe] avatar reflejo 'pe' una vez en este turno."
        "[obs:voseo] avatar uso forma vos (decis/tenes) una vez en este turno."
    Confianza tentativa: 0.45-0.55.
  - Solo si el HISTORIAL DE PERSONALIDAD PREVIO ya contiene 5 o mas notas con el
    mismo prefijo "[obs:<marcador>]", emiti UNA SOLA nota confirmada (sin prefijo
    [obs:]) que diga que el avatar adopta ese marcador con este usuario. Confianza:
    0.80-0.95.
  - Despues de emitir la nota confirmada, podes seguir reflejando el marcador pero
    NO sigas emitiendo "[obs:]" adicionales para ese mismo marcador.

REGLAS GENERALES:
1. Cada nota describe un patron del AVATAR, no un hecho del usuario.
2. Solo registra patrones que sean claros en ESTE turno o coherentes con el historial previo.
3. Maximo 3 notas por turno. Si no hay patron nuevo, devuelve lista vacia.
4. Cada nota: oracion corta y concisa (maximo 200 caracteres).
5. Para patrones NO dialectales: confianza 0.5-0.8 (incipientes) o 0.8-1.0 (establecidos).
6. Para marcadores dialectales: seguir el guardarriel de arriba (tentativos 0.45-0.55, confirmados 0.80+).

ANTI-AUTORREFUERZO (regla critica para evitar deriva de estilo):
Lo que el avatar dice por si mismo NO es evidencia del estilo del usuario.
Una palabra, jerga o registro que aparece SOLO en la respuesta del avatar y
NO en el mensaje del usuario debe tratarse como una eleccion del avatar, no
como reflejo del usuario. Solo se vuelve evidencia del estilo del usuario
cuando el usuario:
  - la repite explicitamente,
  - la confirma ("si, exacto", "tal cual"),
  - o la contradice (eso si es senal — significa que NO es su estilo).
Si una jerga aparece por primera vez en la respuesta del avatar, NO la
registres como patron establecido del usuario en esta nota. Como mucho
emiti una observacion tentativa siguiendo el guardarriel dialectal.

HISTORIAL DE PERSONALIDAD PREVIO:
{prior_persona}

TURNO ACTUAL:
Usuario: {user_message}
Avatar: {assistant_response}

{format_instructions}"""


# ── Chain class ──────────────────────────────────────────────────────────


class PersonaEvolutionChain:
    """LangChain chain for tracking the avatar's evolving personality.

    Analyzes each conversation turn and extracts short notes about recurring
    patterns in the avatar's tone, style, and relational dynamics with a
    specific user. These accumulate over time to give the avatar a consistent,
    deepening voice.

    Attributes:
        llm: The LangChain chat model for analysis.
        parser: Pydantic output parser for structured results.
        chain: The composed LCEL chain.
        min_confidence: Minimum confidence threshold for accepting notes.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        min_confidence: float = 0.4,
    ) -> None:
        """Initialize the persona evolution chain.

        Args:
            llm: A LangChain BaseChatModel instance.
            min_confidence: Minimum confidence score to keep a note.
        """
        self.llm = llm
        self.min_confidence = min_confidence
        self.parser = PydanticOutputParser(pydantic_object=PersonaNotes)

        self.prompt = ChatPromptTemplate.from_messages(
            [("system", _PERSONA_EVOLUTION_TEMPLATE)]
        )
        self.chain = self.prompt | self.llm | self.parser

    @traceable(name="evolve_persona", run_type="chain")
    async def evolve(
        self,
        user_message: str,
        assistant_response: str,
        prior_persona: list[str] | None = None,
    ) -> list[PersonaNote]:
        """Analyze a conversation turn and return persona evolution notes.

        Args:
            user_message: The user's message in this turn.
            assistant_response: The avatar's reply in this turn.
            prior_persona: Existing persona notes as plain strings, for context.

        Returns:
            List of PersonaNote objects above the confidence threshold.
        """
        prior_text = (
            "\n".join(f"- {n}" for n in prior_persona)
            if prior_persona
            else "Sin historial previo."
        )
        try:
            result: PersonaNotes = await self.chain.ainvoke(
                {
                    "user_message": user_message,
                    "assistant_response": assistant_response,
                    "prior_persona": prior_text,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )

            filtered = [
                note
                for note in result.notes
                if note.confidence >= self.min_confidence
            ]

            logger.info(
                "Persona evolution: %d notes extracted (%d kept) for this turn",
                len(result.notes),
                len(filtered),
            )
            return filtered

        except Exception:
            logger.exception("Persona evolution chain failed — skipping")
            return []
