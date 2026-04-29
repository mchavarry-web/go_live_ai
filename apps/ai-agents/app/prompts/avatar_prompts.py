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


def _build_language_style_section(
    country: str | None = None,
    formality_level: float | None = None,
    custom_expressions: list[str] | None = None,
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

    Returns:
        A formatted instruction block for the avatar's dialect, or empty.
    """
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


def _build_behavior_section(behavior_settings: dict[str, object] | None) -> str:
    """Build the behavior preferences section for the system prompt.

    Args:
        behavior_settings: Dictionary with tone, language, and topic preferences.

    Returns:
        A formatted string block for behavior instructions, or empty string.
    """
    if not behavior_settings:
        return ""

    lines = ["\nPREFERENCIAS DE COMPORTAMIENTO:"]

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

    # Language
    language = behavior_settings.get("language", "es")
    if language == "en":
        lines.append("- Responde en inglés (English)")
    elif language == "pt":
        lines.append("- Responde en portugués (Português)")
    elif language == "es":
        lines.append("- Responde en español")

    # Preferred topics
    preferred = behavior_settings.get("preferred_topics", [])
    if preferred and isinstance(preferred, list):
        lines.append(f"- Temas que le interesan especialmente: {', '.join(preferred)}")

    # Restricted topics
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
    knowledge_level: int = 1,
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
    behavior_section = _build_behavior_section(behavior_settings)
    language_style_section = _build_language_style_section(
        country=country,
        formality_level=formality_level,
        custom_expressions=custom_expressions,
    )
    datetime_str = current_datetime or ""

    try:
        formatted = template.format(
            avatar_name=avatar_name,
            display_name=display_name,
            age_range=age_range_str,
            interests=interests_str,
            personality_section=personality_section,
            social_section=social_section,
            health_section=health_section,
            insights_section=insights_section,
            persona_section=persona_section,
            knowledge_level=knowledge_level,
            current_datetime=datetime_str,
            language_style_section=language_style_section,
        )
    except KeyError as exc:
        logger.error("Failed to format avatar system prompt: missing key %s", exc)
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
