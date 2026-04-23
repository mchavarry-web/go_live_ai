"""Enumerations shared across the AI Agents service."""

from enum import Enum


class InsightCategory(str, Enum):
    """Categories for user insights extracted from conversations.

    Each category represents a different aspect of user knowledge
    that the avatar learns over time.

    ``AVATAR_EVOLUTION`` is special: it stores notes about the avatar's
    own emerging voice and style with this particular user, not facts
    about the user. It is kept separate so it can be injected into a
    dedicated prompt section without mixing with user facts.
    """

    PERSONAL_HISTORY = "personal_history"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    EMOTION = "emotion"
    HEALTH = "health"
    AVATAR_EVOLUTION = "avatar_evolution"
    LANGUAGE_STYLE = "language_style"


class LLMProvider(str, Enum):
    """Supported LLM providers via LangChain.

    The provider determines which LangChain chat model wrapper
    is instantiated by the LLM factory.
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class Sentiment(str, Enum):
    """Sentiment labels for message analysis.

    Used by the SentimentChain to classify the overall
    sentiment of a user message.
    """

    POSITIVE = "positivo"
    NEGATIVE = "negativo"
    NEUTRAL = "neutro"
