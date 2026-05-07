"""Avatar system prompt builder.

Constructs the dynamic system prompt for the avatar based on user profile,
social network data, health data, and previously extracted insights.
The resulting string is passed to ChatPromptTemplate as the system message.
"""

import logging
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from app.prompts.dialect_catalog import get_dialect

logger = logging.getLogger(__name__)

# Resolve the template file path relative to this module
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_AVATAR_TEMPLATE_PATH = _TEMPLATE_DIR / "avatar_system.txt"


def _load_template() -> str:
    """Load the avatar system prompt template from disk.

    Returns:
        The raw template string with format placeholders.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    if not _AVATAR_TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Avatar system template not found at {_AVATAR_TEMPLATE_PATH}"
        )
    return _AVATAR_TEMPLATE_PATH.read_text(encoding="utf-8")


def _build_social_section(social_data: dict[str, object] | None) -> str:
    """Build the social data section for the system prompt.

    Args:
        social_data: Dictionary with social network data, or None.

    Returns:
        A formatted string block for social context, or empty string.
    """
    if not social_data:
        return ""

    lines = ["DATOS SOCIALES:"]
    for key, value in social_data.items():
        label = key.replace("_", " ").capitalize()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _build_health_section(health_data: dict[str, object] | None) -> str:
    """Build the health data section for the system prompt.

    Args:
        health_data: Dictionary with health/activity data, or None.

    Returns:
        A formatted string block for health context, or empty string.
    """
    if not health_data:
        return ""

    lines = ["DATOS DE SALUD:"]
    for key, value in health_data.items():
        label = key.replace("_", " ").capitalize()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _build_insights_section(insights: list[str] | None) -> str:
    """Build the insights/memory section for the system prompt.

    Args:
        insights: List of insight strings from vector memory, or None.

    Returns:
        A formatted string block for insights, or a fallback message.
    """
    if not insights:
        return "Aún no conoces mucho sobre esta persona. Haz preguntas para conocerla mejor."

    lines = []
    for insight in insights:
        lines.append(f"- {insight}")
    return "\n".join(lines)


# ── Mode section (the strongest constraint) ─────────────────────────────
#
# The user picks one of three modes (Profesional / Amigos / Citas) from the
# Perfil screen. Switching is seamless — the very next reply reflects the new
# mode. The block returned here sits near the top of the system prompt so it
# anchors interpretation of everything that follows.
#
# Citas internally branches by ``mode_message_count`` (lifetime user messages
# in dating mode) so the avatar starts conservative and warms up gradually.

_MODE_PROFESIONAL = """\
MODO ACTIVO: PROFESIONAL
Tu interaccion con esta persona es estrictamente profesional. Respeta esto sin excepcion:
- NO uses jerga regional ni particulas dialectales (pe, che, vos, po, mero, guey, parce, etc.).
- NO uses voseo ni tuteo demasiado casual; el registro es neutro y formal.
- Mantene respuestas estructuradas, claras y concisas.
- NO introduzcas humor, bromas internas ni apodos. Si el usuario lo invita, respondes con humor sobrio.
- NO compartas hechos personales sensibles (salud, pareja, emociones, vida amorosa) sin que el usuario los pida explicitamente en este turno, aunque los tengas en memoria.
- Trata al usuario con respeto: usa "tu" neutro o "usted" si el contexto lo pide.
"""

_MODE_AMIGOS = """\
MODO ACTIVO: AMIGOS
Tu interaccion con esta persona es relajada, amistosa y de confianza:
- Tono casual permitido. Jerga regional, particulas dialectales y modismos del usuario son bienvenidos cuando ya estan establecidos en el historial de personalidad.
- Humor, ironia, bromas internas y referencias compartidas son apropiados.
- Podes compartir opiniones, recomendaciones y observaciones personales con tacto.
- Tu personalidad puede evolucionar libremente con esta persona segun el guardarriel del PersonaEvolutionChain.
"""

_MODE_CITAS_NASCENT = """\
MODO ACTIVO: CITAS (etapa inicial)
Es una conversacion de cita o coqueteo que recien empieza. Sostene un equilibrio:
- Cordial, atento, presente. Mostra interes genuino sin invadir.
- Coqueteo MUY ligero solo si el usuario lo invita; nunca arranques con flirteo.
- NO uses apodos, terminos de carino ni lenguaje posesivo ("amor", "bebe", "mi vida", "linda/o", etc.).
- NO uses contenido sexual ni insinuacion explicita.
- NO uses jerga regional aun; mantenete en registro neutro-amable.
- NO supongas exclusividad ni intimidad que el usuario no haya marcado.
- Hace preguntas abiertas para conocer al otro, no monologos sobre vos.
"""

_MODE_CITAS_WARMING = """\
MODO ACTIVO: CITAS (etapa media — ya hay confianza)
Hay historia con esta persona. La conversacion puede aflojar:
- Coqueteo ligero permitido si el usuario lo marca; sigue siendo respetuoso.
- Apodos suaves (linda, lindo) son aceptables si el usuario ya los uso o respondio bien a ellos.
- Bromas internas y referencias a charlas previas son bienvenidas.
- Jerga regional permitida si ya esta establecida en el historial de personalidad.
- Sigue evitando lenguaje posesivo o contenido sexual explicito a menos que el usuario lo abra.
"""

_MODE_CITAS_ESTABLISHED = """\
MODO ACTIVO: CITAS (etapa establecida)
La relacion lleva mucho intercambio. Podes ser mucho mas relajado:
- Tono casual y carinoso permitido. Apodos, bromas, codigo compartido OK.
- Adoptar el dialecto y jerga del usuario sin reservas si ya esta confirmado en el historial.
- Sigue siendo respetuoso, sin presionar. Lo sexual explicito sigue requiriendo invitacion clara del usuario.
"""


def _build_mode_section(active_mode: str, mode_message_count: int = 0) -> str:
    """Return the mode-specific behavior block for the system prompt.

    The mode is the strongest single signal in the prompt — it constrains
    tone, register, dialect mirroring and what facts the avatar volunteers.
    Citas internally branches by message count to ramp from conservative
    (nascent) → familiar (warming) → relaxed (established).

    Args:
        active_mode: One of "professional", "friends", "dating".
        mode_message_count: Lifetime user messages in this mode. Only used
            by dating-mode for ramp selection; ignored otherwise.

    Returns:
        A formatted block, or a friends fallback for unknown modes.
    """
    if active_mode == "professional":
        return _MODE_PROFESIONAL
    if active_mode == "dating":
        if mode_message_count < 30:
            return _MODE_CITAS_NASCENT
        if mode_message_count < 150:
            return _MODE_CITAS_WARMING
        return _MODE_CITAS_ESTABLISHED
    # friends + any unknown value falls through to the relaxed default.
    return _MODE_AMIGOS


def _build_persona_section(persona_insights: list[str] | None) -> str:
    """Build the avatar's own evolving persona section for the system prompt.

    These are not facts about the user but notes about how the avatar's
    voice, style and relationship with this person has been taking shape.

    Tentative dialect-marker observations are stored with an ``[obs:<marker>]``
    prefix by ``PersonaEvolutionChain``. They exist only as evidence the chain
    counts before promoting a marker to a confirmed adoption note. They are
    NOT injected into the avatar's prompt — the avatar should not start
    mirroring a regional particle just because it appeared once or twice.
    See ``app/chains/persona_evolution_chain.py`` for the full guardrail.

    Args:
        persona_insights: List of persona evolution strings, or None.

    Returns:
        A formatted string block for the avatar's self-model, or empty string.
    """
    if not persona_insights:
        return ""

    confirmed = [n for n in persona_insights if not n.lstrip().startswith("[obs:")]
    if not confirmed:
        return ""

    lines = ["TU VOZ Y EVOLUCIÓN CON ESTA PERSONA:"]
    for note in confirmed:
        lines.append(f"- {note}")
    return "\n".join(lines)


def _build_events_section(
    upcoming_events: list[dict[str, str | bool]] | None,
    display_name: str,
) -> str:
    """Build the upcoming-events section for the system prompt.

    Renders pre-humanized event entries (produced by
    ``event_humanizer.serialize_events_for_prompt`` at profile-build time)
    as a short block. The block is omitted entirely when there are no
    upcoming events — the avatar should not be told "no events" because
    that invites it to volunteer the absence unprompted.

    Args:
        upcoming_events: List of dicts with ``title``, ``when_human``,
            ``when_iso``, and ``has_time`` keys, or None.
        display_name: User's display name (used in the header).

    Returns:
        A formatted string block for upcoming events, or empty string.
    """
    if not upcoming_events:
        return ""

    lines = [f"PRÓXIMOS COMPROMISOS DE {display_name}:"]
    for ev in upcoming_events:
        lines.append(f"- {ev.get('when_human', '')}: {ev.get('title', '')}")
    lines.append(
        "Si la persona menciona alguno o pregunta por su agenda, refiérete a él "
        "naturalmente (no como una lista). Si está cerca, podés recordárselo de "
        "manera amistosa."
    )
    return "\n".join(lines)


def _mode_demands_neutral_register(active_mode: str, mode_message_count: int) -> bool:
    """Whether the active mode requires the avatar to drop dialect/casual cues.

    Profesional and the nascent stage of Citas ban regional slang, voseo and
    casual humor outright. We use this gate to suppress the language-style
    and tone-preference sections so they cannot contradict the mode block
    later in the prompt.
    """
    if active_mode == "professional":
        return True
    if active_mode == "dating" and mode_message_count < 30:
        return True
    return False


def _build_language_style_section(
    country: str | None = None,
    formality_level: float | None = None,
    custom_expressions: list[str] | None = None,
    active_mode: str = "friends",
    mode_message_count: int = 0,
) -> str:
    """Build the language style / dialect adaptation section.

    Uses the dialect catalog to select appropriate slang and conjugation
    based on the user's country and detected formality level.

    Args:
        country: ISO 3166-1 alpha-2 country code (e.g. "ar", "pe").
        formality_level: Detected formality from 0.0 (very informal) to
            1.0 (very formal). Drives slang intensity selection.
        custom_expressions: Extra expressions detected from the user's
            messages that may not be in the catalog.
        active_mode: Current avatar mode. Profesional and dating-nascent
            suppress this section so dialect/voseo/jerga can't override
            the mode block's neutral-register rules.
        mode_message_count: Lifetime user messages in this mode; used only
            to distinguish dating-nascent (< 30) from later dating stages.

    Returns:
        A formatted instruction block for the avatar's dialect, or empty.
    """
    if _mode_demands_neutral_register(active_mode, mode_message_count):
        return ""

    dialect = get_dialect(country)
    if not dialect:
        return ""

    effective_formality = formality_level if formality_level is not None else 0.5

    if effective_formality < 0.4:
        slang_list = dialect["slang_casual"]
        intensity_label = "Usa jerga libremente, el usuario habla muy informal."
    elif effective_formality < 0.7:
        slang_list = dialect["slang_moderate"]
        intensity_label = "Usa jerga moderada, el usuario es semi-informal."
    else:
        slang_list = []
        intensity_label = "El usuario habla formal. Evita jerga pesada, mantén un tono respetuoso pero cercano."

    lines = [
        f"ADAPTACIÓN LINGÜÍSTICA — dialecto {dialect['name']}:",
        f"- Pronombre: {dialect['pronoun']}",
        f"- Conjugación: {dialect['conjugation_hint']}",
        f"- {intensity_label}",
    ]

    if slang_list:
        lines.append(f"- Expresiones que puedes usar: {', '.join(slang_list)}")

    if dialect["fillers"]:
        lines.append(f"- Muletillas naturales: {', '.join(dialect['fillers'])}")

    if custom_expressions:
        lines.append(
            f"- Expresiones propias del usuario (usa estas también): {', '.join(custom_expressions)}"
        )

    if dialect["avoid"]:
        lines.append(
            f"- EVITA expresiones de otros dialectos: {', '.join(dialect['avoid'])}"
        )

    return "\n".join(lines)


def _build_transcript_quotes_section(transcript_quotes: list[str] | None) -> str:
    """Surface verbatim quotes from the user's audio journal (Phase 14).

    Distinct from the insights section which surfaces *derived facts*;
    this section surfaces *what the user actually said* in their voice
    journal so the avatar can reference it without inventing language.

    Args:
        transcript_quotes: Raw quote strings, or None.

    Returns:
        A short labelled block, or empty string when no quotes qualified.
    """
    if not transcript_quotes:
        return ""
    lines = ["FRAGMENTOS RELEVANTES DE LO QUE HA DICHO:"]
    for quote in transcript_quotes:
        clean = quote.strip().replace("\n", " ")
        if len(clean) > 280:
            clean = clean[:277].rstrip() + "..."
        lines.append(f'- "{clean}"')
    lines.append(
        "Podés hacer referencia a estos contenidos de manera natural, "
        "sin citar literalmente ni decir 'dijiste exactamente'."
    )
    return "\n".join(lines)


def _build_summary_section(prior_summary: str | None) -> str:
    """Build the medium-term conversation-summary section (Phase 13).

    Surfaced when ``ConversationSummaryService.latest_summary_text`` returns
    a non-empty value. Inserted between the long-term insights pool and
    the short-term recent history sent to the chain — fills the
    "what was discussed earlier in this thread" gap that long
    conversations otherwise lose.

    Args:
        prior_summary: Stored summary text, or None.

    Returns:
        A formatted block, or empty string when there's nothing to surface.
    """
    if not prior_summary or not prior_summary.strip():
        return ""
    return (
        "RESUMEN DE LA CONVERSACIÓN HASTA AHORA:\n"
        f"{prior_summary.strip()}\n"
        "Usá este resumen como contexto sin repetirlo verbatim. La memoria "
        "de mediano plazo está acá; los últimos turnos van por separado."
    )


def _build_agent_identity_section(
    agent_identity: str | None, display_name: str
) -> str:
    """Build the agent-identity / representation section (Wave C.1, 2026-05-06).

    The avatar's posture changes when it operates as something other
    than the default conversational companion. Modes:

    - ``companion`` — the historical default. The avatar is "your
      avatar, not you". Section is omitted.
    - ``representative`` — the avatar acts as the user's authorized
      proxy for read-only capabilities.
    - ``draft`` — the avatar drafts actions; the user must approve.
    - ``autopilot`` — pre-approved write actions for specific
      capabilities. Should never be silent.

    See ``docs/autonomous_agent_design.md`` for the full policy.
    """
    if not agent_identity or agent_identity == "companion":
        return ""
    label_by_mode = {
        "representative": (
            "MODO REPRESENTANTE: estás operando como el representante autorizado de "
            f"{display_name}. Usá las herramientas de lectura permitidas; cualquier "
            "accion que requiera escribir o tener efectos externos requiere aprobacion previa."
        ),
        "draft": (
            f"MODO BORRADOR: estás preparando acciones para que {display_name} las apruebe "
            "antes de ejecutarse. NO ejecutes herramientas con efectos externos. "
            "Devolvé propuestas estructuradas y esperá aprobacion."
        ),
        "autopilot": (
            f"MODO PILOTO AUTOMATICO: tenés permiso pre-aprobado para una accion especifica "
            f"de {display_name}. Limitate al alcance autorizado y registrá la accion. "
            "Cualquier desviacion fuera del alcance debe volver a modo BORRADOR."
        ),
    }
    text = label_by_mode.get(agent_identity)
    if text is None:
        return ""
    return text


def _build_location_section(last_location: dict[str, float | str] | None) -> str:
    """Build the reactive-location section for the system prompt.

    Privacy-gated by Rails (``User.share_location_with_avatar``). When
    enabled, the prompt receives the user's latest known coordinates so
    the avatar can answer "qué hago hoy en Lima"-type questions naturally
    without resorting to a generic answer.

    Coords-only by design: we don't reverse-geocode here. The LLM handles
    "the user is at -12.04, -77.04, country=pe" → "Lima, Peru" inference
    on its own, and avoiding a geocoding dependency keeps the dev path
    cheap and the privacy surface small.

    Args:
        last_location: Dict with optional ``latitude``, ``longitude``,
            ``country``, ``city`` keys, or None.

    Returns:
        A short Spanish "UBICACIÓN ACTUAL" line, or empty string when
        no location is available.
    """
    if not last_location:
        return ""

    lat = last_location.get("latitude")
    lng = last_location.get("longitude")
    country = last_location.get("country")
    city = last_location.get("city")

    parts: list[str] = []
    if city:
        parts.append(str(city))
    if country:
        parts.append(str(country).upper())
    if lat is not None and lng is not None:
        try:
            parts.append(f"({float(lat):.3f}, {float(lng):.3f})")
        except (TypeError, ValueError):
            pass
    if not parts:
        return ""
    return "UBICACIÓN ACTUAL DEL USUARIO: " + " ".join(parts) + "."


def _build_formality_directive_section(
    formality_level: float | None,
    active_mode: str,
    mode_message_count: int,
    behavior_settings: dict[str, object] | None,
) -> str:
    """Translate detected ``formality_level`` into an explicit register directive.

    The slang calibrator chain produces a 0.0–1.0 reading from the user's
    own messages every 5 turns. Until this section, that signal lived only
    in ``_build_language_style_section`` to bin slang intensity — the avatar
    received no explicit instruction about register. This section closes
    that gap.

    Suppression rules:
    - Profesional mode and dating-nascent already enforce neutral register;
      adding a directive on top would either be redundant or contradict the
      mode block. Suppress in those cases.
    - When ``behavior_settings.tone_formality`` is set, the user's explicit
      policy wins over the calibrator's observation; suppress so
      ``_build_behavior_section`` is the sole formality voice.

    Args:
        formality_level: 0.0 (very informal) to 1.0 (very formal), or None.
        active_mode: Current avatar mode.
        mode_message_count: Lifetime user-message count in active_mode.
        behavior_settings: Optional explicit behavior policy.

    Returns:
        A short directive paragraph, or empty string.
    """
    if formality_level is None:
        return ""
    if _mode_demands_neutral_register(active_mode, mode_message_count):
        return ""
    if behavior_settings and behavior_settings.get("tone_formality") is not None:
        return ""

    if formality_level < 0.3:
        directive = (
            "REGISTRO DETECTADO: muy informal. "
            "Tutea libremente, contracciones permitidas, jerga regional sin reservas. "
            "El usuario habla relajado — espejá ese registro."
        )
    elif formality_level < 0.7:
        directive = (
            "REGISTRO DETECTADO: neutro-cercano. "
            "Contracciones ok, jerga moderada. Mantén calidez sin caer en exceso de coloquialismo."
        )
    else:
        directive = (
            "REGISTRO DETECTADO: más formal. "
            "Trato respetuoso, evita jerga pesada y muletillas excesivas. "
            "Cercanía sin tutearse de más."
        )
    return directive


def _build_behavior_section(
    behavior_settings: dict[str, object] | None,
    active_mode: str = "friends",
    mode_message_count: int = 0,
) -> str:
    """Build the behavior preferences section for the system prompt.

    This block is appended to the END of the system prompt, so it's the most
    recent instruction the model sees. To stop it from softening the mode
    block's strict-register rules, we suppress tone-shaping lines (formality,
    humor, verbosity, preferred_topics) when the active mode demands a
    neutral register. ``language`` and ``restricted_topics`` always pass
    through — they're safety/policy, not register.

    Args:
        behavior_settings: Dictionary with tone, language, and topic preferences.
        active_mode: Current avatar mode.
        mode_message_count: Lifetime user messages in the active mode.

    Returns:
        A formatted string block for behavior instructions, or empty string.
    """
    if not behavior_settings:
        return ""

    suppress_tone = _mode_demands_neutral_register(active_mode, mode_message_count)
    lines = ["\nPREFERENCIAS DE COMPORTAMIENTO:"]

    if not suppress_tone:
        # Tone formality
        formality = behavior_settings.get("tone_formality", 0.5)
        if isinstance(formality, (int, float)):
            if formality < 0.3:
                lines.append("- Tono: Muy casual y relajado")
            elif formality < 0.5:
                lines.append("- Tono: Casual y cercano")
            elif formality > 0.7:
                lines.append("- Tono: Formal y respetuoso")
            # else: default, no instruction needed

        # Humor
        humor = behavior_settings.get("tone_humor", 0.5)
        if isinstance(humor, (int, float)):
            if humor > 0.7:
                lines.append("- Usa humor y bromas con frecuencia")
            elif humor < 0.3:
                lines.append("- Mantén un tono serio, evita bromas")

        # Verbosity
        verbosity = behavior_settings.get("tone_verbosity", 0.5)
        if isinstance(verbosity, (int, float)):
            if verbosity > 0.7:
                lines.append("- Sé detallado y extenso en tus respuestas")
            elif verbosity < 0.3:
                lines.append("- Sé breve y conciso en tus respuestas")

    # Language preference always passes through.
    language = behavior_settings.get("language", "es")
    if language == "en":
        lines.append("- Responde en inglés (English)")
    elif language == "pt":
        lines.append("- Responde en portugués (Português)")
    elif language == "es":
        lines.append("- Responde en español")

    if not suppress_tone:
        # Preferred topics — feels casual/conversational, suppress in strict modes.
        preferred = behavior_settings.get("preferred_topics", [])
        if preferred and isinstance(preferred, list):
            lines.append(f"- Temas que le interesan especialmente: {', '.join(preferred)}")

    # Restricted topics always pass through (safety/policy, not register).
    restricted = behavior_settings.get("restricted_topics", [])
    if restricted and isinstance(restricted, list):
        lines.append(f"- NO toques estos temas: {', '.join(restricted)}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _build_personality_section(
    introvert_extrovert: float | None = None,
    rational_emotional: float | None = None,
    values: list[str] | None = None,
) -> str:
    """Build the personality traits section for the system prompt.

    Args:
        introvert_extrovert: Scale from 0.0 (introvert) to 1.0 (extrovert).
        rational_emotional: Scale from 0.0 (rational) to 1.0 (emotional).
        values: List of user's core values.

    Returns:
        A formatted string block for personality, or empty string.
    """
    lines: list[str] = []

    if introvert_extrovert is not None:
        if introvert_extrovert < 0.3:
            lines.append("- Personalidad: Introvertido/a — prefiere conversaciones tranquilas y reflexivas")
        elif introvert_extrovert < 0.5:
            lines.append("- Personalidad: Ligeramente introvertido/a")
        elif introvert_extrovert > 0.7:
            lines.append("- Personalidad: Extrovertido/a — disfruta interacciones dinamicas y sociales")
        elif introvert_extrovert > 0.5:
            lines.append("- Personalidad: Ligeramente extrovertido/a")

    if rational_emotional is not None:
        if rational_emotional < 0.3:
            lines.append("- Estilo: Muy racional y analitico — valora datos y logica")
        elif rational_emotional < 0.5:
            lines.append("- Estilo: Tiende a lo racional")
        elif rational_emotional > 0.7:
            lines.append("- Estilo: Muy emocional y empatico — valora sentimientos y conexion")
        elif rational_emotional > 0.5:
            lines.append("- Estilo: Tiende a lo emocional")

    if values:
        lines.append(f"- Valores: {', '.join(values)}")

    if not lines:
        return ""

    return "RASGOS DE PERSONALIDAD:\n" + "\n".join(lines)


def build_avatar_system_prompt(
    avatar_name: str,
    display_name: str,
    knowledge_level: int = 1,  # 1-10 from Rails Avatar; rendered as 1-5 in prompt
    age_range: str | None = None,
    interests: list[str] | None = None,
    introvert_extrovert: float | None = None,
    rational_emotional: float | None = None,
    values: list[str] | None = None,
    social_data: dict[str, object] | None = None,
    health_data: dict[str, object] | None = None,
    insights: list[str] | None = None,
    persona_insights: list[str] | None = None,
    behavior_settings: dict[str, object] | None = None,
    current_datetime: str | None = None,
    country: str | None = None,
    formality_level: float | None = None,
    custom_expressions: list[str] | None = None,
    active_mode: str = "friends",
    mode_message_count: int = 0,
    upcoming_events: list[dict[str, str | bool]] | None = None,
    last_location: dict[str, float | str] | None = None,
    prior_summary: str | None = None,
    transcript_quotes: list[str] | None = None,
    agent_identity: str | None = None,
) -> str:
    """Build the full avatar system prompt from user profile and context.

    Reads the template file from ``templates/avatar_system.txt`` and fills
    in all dynamic sections with the provided user data.

    Args:
        avatar_name: The avatar's display name.
        display_name: The user's display name.
        knowledge_level: Avatar's knowledge depth about the user (1-5).
        age_range: User's age range bucket (e.g. "25_34"), or None.
        interests: List of user interests, or None.
        introvert_extrovert: Personality scale (0.0=introvert, 1.0=extrovert).
        rational_emotional: Personality scale (0.0=rational, 1.0=emotional).
        values: User's core values.
        social_data: Social network context data, or None.
        health_data: Health/activity context data, or None.
        insights: Previously extracted insight strings about the user, or None.
        persona_insights: Avatar's own evolving voice/style notes, or None.
        behavior_settings: Avatar behavior preferences, or None.
        current_datetime: Human-readable current date and time string.
            If None, the template placeholder is filled with an empty string.
        country: ISO 3166-1 alpha-2 code for dialect selection.
        formality_level: Detected user formality (0.0-1.0) from language
            style insights.
        custom_expressions: Extra user-specific expressions detected at
            runtime by the slang calibrator.

    Returns:
        The fully formatted system prompt string.
    """
    template = _load_template()

    interests_str = ", ".join(interests) if interests else "No especificados"
    age_range_str = age_range if age_range else "No especificado"
    personality_section = _build_personality_section(
        introvert_extrovert=introvert_extrovert,
        rational_emotional=rational_emotional,
        values=values,
    )
    social_section = _build_social_section(social_data)
    health_section = _build_health_section(health_data)
    insights_section = _build_insights_section(insights)
    persona_section = _build_persona_section(persona_insights)
    events_section = _build_events_section(upcoming_events, display_name)
    location_section = _build_location_section(last_location)
    summary_section = _build_summary_section(prior_summary)
    transcript_quotes_section = _build_transcript_quotes_section(transcript_quotes)
    agent_identity_section = _build_agent_identity_section(
        agent_identity, display_name
    )
    formality_directive_section = _build_formality_directive_section(
        formality_level=formality_level,
        active_mode=active_mode,
        mode_message_count=mode_message_count,
        behavior_settings=behavior_settings,
    )
    behavior_section = _build_behavior_section(
        behavior_settings,
        active_mode=active_mode,
        mode_message_count=mode_message_count,
    )
    language_style_section = _build_language_style_section(
        country=country,
        formality_level=formality_level,
        custom_expressions=custom_expressions,
        active_mode=active_mode,
        mode_message_count=mode_message_count,
    )
    mode_section = _build_mode_section(
        active_mode=active_mode,
        mode_message_count=mode_message_count,
    )
    datetime_str = current_datetime or ""

    # Render knowledge_level on a stable 1-5 scale even though the canonical
    # Rails value is 1-10. Mapping is a simple halving: 1-2 → 1, 3-4 → 2,
    # 5-6 → 3, 7-8 → 4, 9-10 → 5. This lets the prompt copy stay "X/5"
    # without changing meaning when the Rails formula evolves.
    knowledge_level_display = max(1, min(5, (int(knowledge_level) + 1) // 2))

    # Sections that may be absent from older deployed templates. The
    # template-fallback path below strips these placeholders out and
    # appends each section to the tail of the formatted prompt instead.
    _OPTIONAL_SECTIONS = {
        "events_section": events_section,
        "formality_directive_section": formality_directive_section,
        "location_section": location_section,
        "summary_section": summary_section,
        "transcript_quotes_section": transcript_quotes_section,
        "agent_identity_section": agent_identity_section,
    }

    def _format_with(template_str: str, **extra: str | int) -> str:
        return template_str.format(
            avatar_name=avatar_name,
            display_name=display_name,
            age_range=age_range_str,
            interests=interests_str,
            personality_section=personality_section,
            social_section=social_section,
            health_section=health_section,
            insights_section=insights_section,
            persona_section=persona_section,
            knowledge_level=knowledge_level_display,
            current_datetime=datetime_str,
            language_style_section=language_style_section,
            mode_section=mode_section,
            **extra,
        )

    try:
        formatted = _format_with(
            template,
            events_section=events_section,
            formality_directive_section=formality_directive_section,
            location_section=location_section,
            summary_section=summary_section,
            transcript_quotes_section=transcript_quotes_section,
            agent_identity_section=agent_identity_section,
        )
    except KeyError as exc:
        missing = str(exc).strip("'")
        if missing in _OPTIONAL_SECTIONS:
            logger.warning(
                "avatar_system.txt template is missing {%s}; appending sections at tail",
                missing,
            )
            stripped = template
            for placeholder in _OPTIONAL_SECTIONS:
                stripped = stripped.replace("{" + placeholder + "}", "")
            formatted = _format_with(stripped)
            for section in _OPTIONAL_SECTIONS.values():
                if section:
                    formatted += "\n\n" + section
        else:
            logger.error(
                "Failed to format avatar system prompt: missing key %s", exc
            )
            raise ValueError(f"Template formatting error: missing key {exc}") from exc

    if behavior_section:
        formatted += "\n" + behavior_section

    logger.debug(
        "Built avatar system prompt for user=%s, avatar=%s (knowledge=%d, country=%s)",
        display_name,
        avatar_name,
        knowledge_level,
        country or "none",
    )
    return formatted


def get_avatar_chat_prompt() -> ChatPromptTemplate:
    """Create a ChatPromptTemplate for avatar conversations.

    Returns a template with:
    - A system message placeholder (``{system_prompt}``) for the dynamic
      system prompt built by ``build_avatar_system_prompt()``.
    - A messages placeholder (``{history}``) for conversation history.
    - A human message placeholder (``{user_message}``) for the current message.

    Returns:
        A ChatPromptTemplate ready for chain composition.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", "{system_prompt}"),
            ("placeholder", "{history}"),
            ("human", "{user_message}"),
        ]
    )
