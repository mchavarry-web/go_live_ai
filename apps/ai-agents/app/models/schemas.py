"""Pydantic models (API schemas) for the AI Agents service.

All request/response contracts between api-backend and this service
are defined here. Models follow Pydantic v2 conventions with strict
validation, immutability where appropriate, and complete type hints.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import InsightCategory, Sentiment


# ── User Profile ────────────────────────────────────────────────────────


class UserProfile(BaseModel):
    """User profile data received from api-backend.

    Frozen (immutable) to prevent accidental mutation during
    chain processing. Whitespace is stripped automatically.

    Attributes:
        display_name: User's display name (1-100 chars).
        avatar_name: Name of the user's avatar (1-50 chars).
        age_range: Optional age range bucket (e.g. "25_34").
        interests: User's interests, stored lowercase and unique.
        knowledge_level: Avatar's knowledge depth about the user (1-5).
        introvert_extrovert: Personality scale (0.0=introvert, 1.0=extrovert).
        rational_emotional: Personality scale (0.0=rational, 1.0=emotional).
        values: User's core values from onboarding.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        frozen=True,
    )

    display_name: str = Field(..., min_length=1, max_length=100)
    avatar_name: str = Field(..., min_length=1, max_length=50)
    age_range: str | None = None
    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code (e.g. 'ar', 'mx', 'pe')",
    )
    timezone: str | None = Field(
        default=None,
        max_length=50,
        description="IANA timezone name (e.g. 'America/Lima'). Used to resolve relative date phrases during event extraction.",
    )
    interests: list[str] = Field(default_factory=list)
    knowledge_level: int = Field(default=1, ge=1, le=5)
    introvert_extrovert: float | None = None
    rational_emotional: float | None = None
    values: list[str] = Field(default_factory=list)
    # User-selected behavior mode. Drives the strongest constraints in the
    # avatar's system prompt (tone, register, dialect-mirroring rules) and
    # scopes persona-evolution insights via the source string.
    active_mode: Literal["professional", "friends", "dating"] = "friends"
    # Lifetime user-message count IN the active mode. Used by the dating-mode
    # ramp (nascent < 30 < warming < 150 ≤ established) to soften register as
    # familiarity grows. Other modes ignore this value.
    mode_message_count: int = Field(default=0, ge=0)

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, v: list[str]) -> list[str]:
        """Ensure interests are lowercase, stripped, and unique."""
        return list({interest.lower().strip() for interest in v})


# ── Chat ────────────────────────────────────────────────────────────────


class ChatGenerateRequest(BaseModel):
    """Request to generate a chat response from the avatar.

    Sent by api-backend when a user sends a message in a conversation.

    Attributes:
        user_id: Unique user identifier.
        message: The user's message text (1-10000 chars).
        conversation_id: Unique conversation identifier.
        user_profile: The user's profile data.
        social_data: Optional data from connected social networks.
        health_data: Optional health and activity data.
        conversation_history: Recent message history as role/content dicts.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: str = Field(..., min_length=1)
    user_profile: UserProfile
    social_data: dict[str, object] | None = None
    health_data: dict[str, object] | None = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    message_created_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the user sent the message. Used as RELATIVE_BASE for event-extraction date resolution.",
    )


class ChatGenerateResponse(BaseModel):
    """Response from chat generation.

    Returned to api-backend after the avatar generates a response.

    Attributes:
        response: The avatar's response text.
        emotion_detected: Primary emotion detected in the user's message.
        new_insights: List of newly extracted insights.
        suggested_followup: Optional suggested follow-up question.
        tokens_used: Total tokens consumed (0 if tracked by LangSmith).
    """

    response: str
    emotion_detected: str | None = None
    new_insights: list["Insight"] = Field(default_factory=list)
    suggested_followup: str | None = None
    tokens_used: int = Field(default=0, ge=0)


# ── Insights ────────────────────────────────────────────────────────────


class Insight(BaseModel):
    """An insight extracted from user interaction.

    Insights are pieces of knowledge the avatar learns about the user
    through conversations and are stored in the vector memory.

    Attributes:
        id: Unique insight identifier.
        user_id: The user this insight belongs to.
        category: Classification category of the insight.
        content: The insight text content (max 1000 chars).
        confidence: Extraction confidence score (0.0 to 1.0).
        source: Origin of the insight (e.g. "conversation").
        created_at: When the insight was extracted.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    category: InsightCategory
    content: str = Field(..., max_length=1000)
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str
    created_at: datetime | None = None


class InsightExtractRequest(BaseModel):
    """Request to extract insights from a text message.

    Attributes:
        user_id: The user whose message is being analyzed.
        message: The text to extract insights from.
        context: Optional prior context about the user.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=10000)
    context: str = ""


# ── User Events ─────────────────────────────────────────────────────────


class UserEvent(BaseModel):
    """A dated event/commitment extracted from a user message.

    Stored in the ``user_events`` table; surfaced to the avatar's system
    prompt via ``EventRepository.list_upcoming`` so the avatar can recall
    appointments by absolute date instead of only through semantic search.

    Attributes:
        id: Unique event identifier.
        user_id: The user this event belongs to.
        title: Short label (max 200 chars).
        occurs_at: Absolute UTC timestamp of the event.
        occurs_at_has_time: False when the user gave only a date.
        raw_text: Verbatim fragment of the user message.
        source: Origin string (e.g. "conversation").
        source_message_id: Optional Rails Message id for traceability.
        confidence: Extraction confidence score (0.0 to 1.0).
        status: One of "active", "cancelled", "archived".
        timezone: IANA tz name used at extraction time.
        created_at: When the event was extracted.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str = Field(..., max_length=200)
    occurs_at: datetime
    occurs_at_has_time: bool = True
    raw_text: str
    source: str
    source_message_id: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: Literal["active", "cancelled", "archived"] = "active"
    timezone: str | None = None
    created_at: datetime | None = None


class UserEventCreate(BaseModel):
    """Internal payload for creating a user event from extraction output.

    Used by ``ChatService._extract_and_store_events`` to hand a resolved
    event from the extraction chain to the repository.

    Attributes:
        title: Short label (max 200 chars).
        occurs_at: Absolute UTC timestamp of the event.
        occurs_at_has_time: False when the user gave only a date.
        raw_text: Verbatim fragment of the user message.
        source: Origin string (e.g. "conversation").
        source_message_id: Optional Rails Message id.
        confidence: Extraction confidence score.
        timezone: IANA tz name used to resolve relative phrases.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=200)
    occurs_at: datetime
    occurs_at_has_time: bool = True
    raw_text: str = Field(..., min_length=1, max_length=500)
    source: str = "conversation"
    source_message_id: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    timezone: str | None = None


class SocialPost(BaseModel):
    """A single post from a social media platform."""

    text: str = Field(..., min_length=1)
    is_repost: bool = False
    date: str = ""
    media_types: list[str] = Field(default_factory=list)


class SocialExtractRequest(BaseModel):
    """Request to extract insights from social media data in batch.

    Two shapes are accepted:
      1. Legacy "posts/bio" shape — used by the generic SocialMediaInsightChain.
      2. Platform-specific raw `data` payload — used by the per-platform
         chains (Facebook, Twitter, Spotify). Rails populates `data` from the
         provider-specific response stashed on `SocialConnection.metadata.raw_data`.

    Attributes:
        user_id: The user whose social data is being analyzed.
        platform: Social media platform (e.g. "twitter", "spotify").
        username: The user's handle on the platform (optional for raw `data`).
        bio: The user's profile description.
        member_since: When the user joined the platform.
        posts: List of posts/tweets to analyze (legacy generic shape).
        data: Platform-specific raw payload (preferred for FB/Twitter/Spotify).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    platform: str = Field(..., min_length=1, max_length=50)
    username: str = ""
    bio: str = ""
    member_since: str = ""
    posts: list[SocialPost] = Field(default_factory=list)
    data: dict[str, object] = Field(default_factory=dict)


# ── Instagram ──────────────────────────────────────────────────────────


class InstagramComment(BaseModel):
    """A single Instagram comment made by the user."""

    text: str = Field(..., min_length=1)
    post_owner: str = ""


class InstagramExtractRequest(BaseModel):
    """Request to extract insights from Instagram data in batch.

    Contains all 5 types of Instagram metadata grouped by category.

    Attributes:
        user_id: The user whose Instagram data is being analyzed.
        comments: User's comments on posts.
        topics: Recommended topics from Instagram.
        following: Usernames the user follows.
        close_friends: Usernames in close friends list.
        blocked: Usernames the user has blocked.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    comments: list[InstagramComment] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    following: list[str] = Field(default_factory=list)
    close_friends: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


# ── Memory ──────────────────────────────────────────────────────────────


class MemoryResponse(BaseModel):
    """Response containing user memory summary.

    Attributes:
        user_id: The user's identifier.
        total_insights: Total number of stored insights.
        knowledge_level: Current avatar knowledge level (1-5).
        insights: List of recent/relevant insights.
    """

    user_id: str
    total_insights: int = Field(default=0, ge=0)
    knowledge_level: int = Field(default=1, ge=1, le=5)
    insights: list[Insight] = Field(default_factory=list)


# ── Sentiment ───────────────────────────────────────────────────────────


class SentimentAnalysis(BaseModel):
    """Result of sentiment analysis on a user message.

    Attributes:
        sentiment: Overall sentiment label.
        primary_emotion: Detected primary emotion.
        intensity: Emotion intensity score (0.0 to 1.0).
        message: The analyzed message text.
    """

    sentiment: Sentiment
    primary_emotion: str
    intensity: float = Field(..., ge=0.0, le=1.0)
    message: str


# ── Semantic Search ─────────────────────────────────────────────────────


class SemanticSearchRequest(BaseModel):
    """Request for semantic similarity search in the vector store.

    Attributes:
        user_id: The user to search insights for.
        query: The search query text.
        top_k: Number of results to return.
        categories: Optional category filter.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=50)
    categories: list[InsightCategory] | None = None


# ── Health ──────────────────────────────────────────────────────────────


class HealthCheckResponse(BaseModel):
    """Response from the health check endpoint.

    Attributes:
        status: Service status ("healthy" or "unhealthy").
        version: Service version string.
        environment: Current deployment environment.
        database: Database connection status ("connected" or "disconnected").
        langsmith: LangSmith tracing status ("enabled" or "disabled").
    """

    status: str
    version: str
    environment: str
    database: str = "disconnected"
    langsmith: str = "disabled"


# ── Proactive Greeting ──────────────────────────────────────────────────


class ProactiveGenerateRequest(BaseModel):
    """Request to generate a proactive greeting from the avatar.

    Sent by api-backend when the user returns to the app after inactivity.
    Unlike ChatGenerateRequest, this is avatar-initiated: the avatar speaks
    first based on the selected skill and user context.

    Attributes:
        user_id: Unique user identifier.
        conversation_id: Unique conversation identifier (newly created).
        user_profile: The user's profile data for personalization.
        skill_id: ID of the proactive skill selected by the backend registry.
        skill_context: Extra context specific to the selected skill
            (e.g. city/lat/lon for weather, topic for news).
        local_time: User's local time in HH:MM format.
        local_date: User's local date in YYYY-MM-DD format.
        absence_minutes: Minutes since the user's last activity.
        conversation_history: Recent message history (usually empty for new sessions).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    conversation_id: str = Field(..., min_length=1)
    user_profile: UserProfile
    skill_id: str = Field(
        ...,
        min_length=1,
        description="ID of the proactive skill selected by the backend registry",
    )
    skill_context: dict[str, object] = Field(
        default_factory=dict,
        description="Skill-specific context (city, coordinates, topic, etc.)",
    )
    local_time: str = Field(
        ...,
        description="User's local time in HH:MM format (e.g. '09:15')",
    )
    local_date: str = Field(
        ...,
        description="User's local date in YYYY-MM-DD format (e.g. '2026-04-14')",
    )
    absence_minutes: int = Field(
        default=30,
        ge=0,
        description="Minutes elapsed since the user's last activity",
    )
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class ProactiveGenerateResponse(BaseModel):
    """Response with the proactive greeting generated by the avatar.

    Attributes:
        greeting: The avatar's proactive greeting text (2-3 sentences).
        emotion: Optional emotion label detected during generation.
        skill_used: ID of the skill that was actually used.
        tokens_used: Total tokens consumed generating the greeting.
    """

    greeting: str
    emotion: str | None = None
    skill_used: str
    tokens_used: int = Field(default=0, ge=0)
