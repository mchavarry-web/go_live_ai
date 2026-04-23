"""Proactive greeting prompt builder.

Constructs the system prompt used when the avatar initiates a conversation
proactively -- when the user returns to the app after a period of inactivity.

Unlike the regular avatar prompt (which responds to user messages), the
proactive prompt instructs the avatar to speak first with a short, natural
greeting tailored to the selected skill and the user's context.
"""

import logging

from app.models.schemas import ProactiveGenerateRequest

logger = logging.getLogger(__name__)

# Time-of-day labels mapped to local hour ranges.
# Must stay in sync with proactive_skills._get_time_of_day in api-back.
_TIME_OF_DAY_LABELS = {
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 22),
    "night": (22, 6),   # includes late night (22:00-05:59)
}

# Skill-specific instructions injected into the system prompt
_SKILL_INSTRUCTIONS: dict[str, str] = {
    "generic_greeting": (
        "Generate a warm and natural greeting. "
        "Acknowledge the time of day and something personal from the user's interests or values. "
        "Do NOT ask 'How are you?' in a generic way -- be specific and creative. "
        "Keep it to 2-3 sentences maximum."
    ),
    "fun_fact": (
        "Share one surprising, specific, and interesting fact related to the user's interests. "
        "Frame it as something you just thought of or found fascinating. "
        "End with a brief question or comment to spark curiosity. "
        "Keep it to 2-3 sentences maximum."
    ),
    "motivation": (
        "Share a short motivational thought or reflection that aligns with the user's values. "
        "In the morning: forward-looking and energizing. At night: reflective and calming. "
        "Make it feel personal, not generic. "
        "Keep it to 2-3 sentences maximum."
    ),
    "news": (
        "You have searched the web for recent news about the user's interests. "
        "The search results are provided in the skill_context. "
        "Summarize the most relevant piece of news in a conversational, excited tone. "
        "Keep it to 2-3 sentences maximum."
    ),
    "wellness_checkin": (
        "Do a gentle emotional check-in based on what you know about the user. "
        "Reference something from recent conversations if available. "
        "Be empathetic and non-intrusive. "
        "Keep it to 2-3 sentences maximum."
    ),
    "weather": (
        "You know the current weather conditions for the user's location (provided in skill_context). "
        "Share the weather in a natural way and suggest an activity that fits the conditions and the user's interests. "
        "Keep it to 2-3 sentences maximum."
    ),
    "local_events": (
        "You found local events or activities in the user's city (provided in skill_context). "
        "Mention one that aligns with the user's interests in a conversational tone. "
        "Keep it to 2-3 sentences maximum."
    ),
    "smart_reminder": (
        "You noticed the user mentioned something important in a past conversation (provided in skill_context). "
        "Follow up on it naturally, as a friend would. "
        "Keep it to 2-3 sentences maximum."
    ),
    "social_summary": (
        "You have a summary of the user's recent social media activity (provided in skill_context). "
        "Reference it naturally and positively. "
        "Keep it to 2-3 sentences maximum."
    ),
    "on_this_day": (
        "You found an interesting historical event from today's date related to the user's interests (provided in skill_context). "
        "Share it as a fun piece of trivia. "
        "Keep it to 2-3 sentences maximum."
    ),
}


def _get_time_of_day(local_time: str) -> str:
    """Determine the time-of-day label from a HH:MM string.

    Matches the franja definitions in api-back/apps/chat/proactive_skills.py:
    morning 06-11, afternoon 12-17, evening 18-21, night 22-05.

    Args:
        local_time: Time string in HH:MM format.

    Returns:
        One of: 'morning', 'afternoon', 'evening', 'night'.
    """
    try:
        hour = int(local_time.split(":")[0])
    except (ValueError, IndexError):
        return "morning"

    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"  # 22:00-05:59


def _get_time_greeting(time_of_day: str, language: str = "es") -> str:
    """Return a localized greeting phrase for the time of day.

    Args:
        time_of_day: One of 'morning', 'afternoon', 'evening', 'night'.
        language: Language code ('es' or 'en').

    Returns:
        Greeting phrase string.
    """
    greetings_es = {
        "morning": "Buenos dias",
        "afternoon": "Buenas tardes",
        "evening": "Buenas noches",
        "night": "Hola",
    }
    greetings_en = {
        "morning": "Good morning",
        "afternoon": "Good afternoon",
        "evening": "Good evening",
        "night": "Hey",
    }
    greetings = greetings_es if language == "es" else greetings_en
    return greetings.get(time_of_day, "Hola")


def _format_absence(absence_minutes: int) -> str:
    """Format the absence duration as a human-readable string.

    Args:
        absence_minutes: Number of minutes since last activity.

    Returns:
        Human-readable string (e.g. 'a couple of hours', 'a few days').
    """
    if absence_minutes < 60:
        return "a little while"
    if absence_minutes < 120:
        return "about an hour"
    if absence_minutes < 480:
        hours = absence_minutes // 60
        return f"about {hours} hours"
    if absence_minutes < 1440:
        return "most of the day"
    days = absence_minutes // 1440
    if days == 1:
        return "a day"
    return f"{days} days"


def _format_skill_context(skill_id: str, skill_context: dict[str, object]) -> str:
    """Format the skill context into a readable block for the prompt.

    For the ``news`` skill, ``news_results`` is rendered as a dedicated
    ``<news_results>`` block so the LLM can clearly identify the search
    output and reference it in the greeting.

    For all other skills, each key-value pair is listed generically inside
    a ``<skill_context>`` block.

    Args:
        skill_id: The active skill ID.
        skill_context: Dict of context data for the skill.

    Returns:
        Formatted string, or empty string if no context.
    """
    if not skill_context:
        return ""

    if skill_id == "news" and "news_results" in skill_context:
        news_text = skill_context["news_results"]
        other = {k: v for k, v in skill_context.items() if k != "news_results"}
        lines: list[str] = []
        lines.append("<news_results>")
        lines.append(str(news_text))
        lines.append("</news_results>")
        if other:
            lines.append("<skill_context>")
            for key, value in other.items():
                lines.append(f"  {key}: {value}")
            lines.append("</skill_context>")
        return "\n".join(lines)

    lines = ["<skill_context>"]
    for key, value in skill_context.items():
        lines.append(f"  {key}: {value}")
    lines.append("</skill_context>")
    return "\n".join(lines)


def build_proactive_system_prompt(request: ProactiveGenerateRequest) -> str:
    """Build the system prompt for a proactive avatar greeting.

    Constructs a complete system prompt instructing the LLM to generate
    a short, natural, personalized greeting based on the selected skill
    and user context.

    Args:
        request: The ProactiveGenerateRequest with user profile and skill data.

    Returns:
        System prompt string ready to be passed to the LLM.
    """
    profile = request.user_profile
    skill_id = request.skill_id
    skill_context = request.skill_context
    local_time = request.local_time
    local_date = request.local_date
    absence_minutes = request.absence_minutes

    time_of_day = _get_time_of_day(local_time)
    time_greeting = _get_time_greeting(time_of_day)
    absence_str = _format_absence(absence_minutes)

    interests_str = (
        ", ".join(profile.interests) if profile.interests else "various topics"
    )
    values_str = (
        ", ".join(profile.values) if profile.values else "personal growth"
    )

    skill_instructions = _SKILL_INSTRUCTIONS.get(
        skill_id,
        _SKILL_INSTRUCTIONS["generic_greeting"],
    )
    skill_context_block = _format_skill_context(skill_id, skill_context)

    prompt = f"""You are {profile.avatar_name}, the personal AI avatar of {profile.display_name}.
You are initiating a conversation proactively -- the user has just opened the app after being away for {absence_str}.

<user_context>
  name: {profile.display_name}
  time_of_day: {time_of_day} ({local_time} on {local_date})
  interests: {interests_str}
  values: {values_str}
  personality: {"more extrovert" if (profile.introvert_extrovert or 0.5) > 0.5 else "more introvert"}, {"more emotional" if (profile.rational_emotional or 0.5) > 0.5 else "more rational"}
  knowledge_level: {profile.knowledge_level}/5 (how well you know this user)
</user_context>
{skill_context_block}

<instructions>
  - You are speaking FIRST. This is your greeting, not a response.
  - Use the time-of-day greeting "{time_greeting}" naturally (not robotically).
  - Address the user by their name: {profile.display_name}.
  - Be warm, natural, and personal -- like a close friend who knows them well.
  - Active skill: {skill_id}
  - Skill instructions: {skill_instructions}
  - NEVER say "Como puedo ayudarte?" or "En que te puedo ayudar?" -- you are greeting, not offering service.
  - Do NOT include any markdown formatting. Plain conversational text only.
  - Language: {"Spanish" if profile.country in ("ar", "mx", "pe", "co", "cl", "es", "uy", "bo", "py", "ec", "ve") else "English"}.
</instructions>

Generate ONLY the greeting message. Do not include any preamble, explanation, or meta-commentary."""

    logger.debug(
        "Built proactive system prompt: skill=%s, time=%s, absence=%dmin",
        skill_id,
        time_of_day,
        absence_minutes,
    )
    return prompt
