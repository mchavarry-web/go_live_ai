"""SQLAlchemy models for the AI Agents service.

Defines the database schema using SQLAlchemy 2.0 declarative style
with async support. Uses pgvector for vector similarity search.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class InsightModel(Base):
    """SQLAlchemy model for user insights with vector embeddings.

    Stores insights extracted from conversations along with their
    embedding vectors for semantic similarity search via pgvector.

    Attributes:
        id: UUID primary key.
        user_id: Foreign reference to the user (from api-backend).
        category: Insight category (personal_history, preference, etc.).
        content: The insight text content.
        confidence: Extraction confidence score (0.0-1.0).
        source: Origin of the insight (e.g. "conversation").
        embedding: Vector embedding for similarity search (1536 dimensions).
        created_at: Timestamp of creation (server-side default).
        updated_at: Timestamp of last update (auto-updated).
    """

    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),  # OpenAI text-embedding-3-small dimension
        nullable=True,
    )
    # Wave B.1 (2026-05-06) — lifecycle status. 'active' is the default;
    # 'superseded' marks a row that's been replaced by a newer fact (kept
    # for audit), 'corrected' marks a row the user explicitly retracted.
    # Retrieval filters status='active' so superseded rows don't surface.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_by_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    # IVFFlat index for fast vector similarity search
    __table_args__ = (
        Index(
            "ix_insights_embedding_ivfflat",
            embedding,
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_insights_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<InsightModel(id={self.id!r}, user_id={self.user_id!r}, "
            f"category={self.category!r})>"
        )


class UserEventModel(Base):
    """SQLAlchemy model for user-mentioned dated events (appointments, commitments).

    Captures time-bound facts the user mentions in conversation — dentist
    appointments, flights, deadlines — so the avatar can recall them by
    absolute date rather than only via semantic search over insights.

    Retrieved by ``EventRepository.list_upcoming`` for inclusion in the
    avatar's system prompt; not embedded for vector search.

    Attributes:
        id: UUID primary key.
        user_id: Foreign reference to the user (from api-backend).
        title: Short label for the event (max 200 chars).
        occurs_at: Absolute UTC timestamp of the event.
        occurs_at_has_time: False when the user gave only a date (no clock);
            renderer omits the time component when False.
        raw_text: Verbatim fragment of the user message the event was extracted
            from. Audit trail and dedupe key.
        source: Origin string, mirrors InsightModel.source convention
            (e.g. "conversation").
        source_message_id: Optional Rails Message id for traceability.
        confidence: Extraction confidence score (0.0-1.0).
        status: One of "active", "cancelled", "archived". Only "active" rows
            surface in upcoming-event retrieval.
        timezone: IANA tz name used to resolve relative phrases at extraction
            time. Stored for forensic use; renderers use the request-time tz.
        created_at: Timestamp of creation (server-side default).
        updated_at: Timestamp of last update (auto-updated).
    """

    __tablename__ = "user_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    occurs_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    occurs_at_has_time: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="conversation",
    )
    source_message_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
    )
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_user_events_user_occurs", "user_id", "occurs_at"),
        Index("ix_user_events_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<UserEventModel(id={self.id!r}, user_id={self.user_id!r}, "
            f"title={self.title!r}, occurs_at={self.occurs_at!r})>"
        )


class AudioTranscriptChunkModel(Base):
    """SQLAlchemy model for embedded slices of an audio transcript.

    Phase 14 — separate retrieval pool from ``insights``. Stores raw
    user-spoken text in N-token windows so the avatar can quote the user
    verbatim when relevant ("you said in your journal that..."). Insights
    remain the derived-summary pool; transcript chunks are the
    source-of-truth pool.

    Wiped together with insights via the GDPR memory-delete path.

    Attributes:
        id: UUID primary key.
        user_id: Foreign reference to the Rails User id.
        audio_chunk_id: Foreign reference to the Rails AudioChunk id.
        audio_session_id: Denormalised Rails AudioSession id; kept on the
            row so per-session wipes can avoid joins.
        sequence_in_chunk: 0..N-1 ordering within one parent chunk.
        text: The transcript window text.
        embedding: 1536-dim OpenAI text-embedding-3-small vector.
        recorded_at: When the parent chunk was recorded (UTC). Indexed
            so the read path can do recency-weighted filtering later.
        created_at: Insert timestamp.
    """

    __tablename__ = "audio_transcript_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    audio_chunk_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    audio_session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    sequence_in_chunk: Mapped[int] = mapped_column(nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_audio_chunks_user_recorded",
            "user_id",
            "recorded_at",
        ),
        Index(
            "ix_audio_chunks_embedding_ivfflat",
            embedding,
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AudioTranscriptChunkModel(id={self.id!r}, "
            f"user_id={self.user_id!r}, seq={self.sequence_in_chunk})>"
        )


class UserStyleProfileModel(Base):
    """Structured user-style profile (Wave B.3 — 2026-05-06).

    Replaces the JSON-blob `language_style` insight with a typed table
    so the prompt builder can read structured fields directly. One row
    per user; updated by ``SlangCalibratorChain`` on every calibration
    pass. The legacy `language_style` insight is kept as a fallback so
    rollout can be staged.

    Fields beyond the original calibrator output (sentence_length_avg,
    common_greetings, fillers, slang_observed, punctuation, emoji,
    humor_style, directness, verbosity, never_says, example_phrases)
    are reserved for richer style modelling — populated as the
    calibrator chain or future style-extractor chains evolve.
    """

    __tablename__ = "user_style_profiles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )
    # Core (populated today by SlangCalibratorChain).
    primary_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    dialect: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    formality_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    emoji_frequency: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    custom_expressions: Mapped[Optional[list[str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    # Reserved (Wave B.3+; default empty/None — write paths added incrementally).
    sentence_length_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    common_greetings: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    common_closings: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    fillers: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    slang_observed: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    punctuation_habits: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    humor_style: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    directness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verbosity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    never_says: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    example_phrases: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<UserStyleProfileModel(user_id={self.user_id!r}, "
            f"formality={self.formality_level}, "
            f"emoji={self.emoji_frequency!r})>"
        )


class ConversationSummaryModel(Base):
    """SQLAlchemy model for medium-term conversation memory.

    Rolling summaries written every N turns by ``ConversationSummaryChain``.
    The avatar reads the most-recent non-superseded summary at chat-time
    and uses it in lieu of older messages, saving tokens on long arcs.

    Attributes:
        id: UUID primary key.
        user_id: Foreign reference to the user.
        conversation_id: Reference to the conversation (from api-backend).
        summary: Summarized text of the conversation (≤ 800 chars).
        message_count: Number of messages summarized.
        summary_token_count: Approximate token count of ``summary`` for
            chat-time budgeting decisions in Phase 13.
        range_start_message_id: First Rails Message id in the window.
        range_end_message_id: Last Rails Message id in the window. Phase
            13 uses this to align the kept-tail of conversation history.
        superseded_at: Set when a later summary subsumes this row. NULL
            means "latest".
        created_at: Timestamp of creation.
    """

    __tablename__ = "conversation_summaries"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    message_count: Mapped[int] = mapped_column(nullable=False, default=0)
    summary_token_count: Mapped[int] = mapped_column(nullable=False, default=0)
    range_start_message_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )
    range_end_message_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_conv_summaries_conv_latest",
            "conversation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ConversationSummaryModel(id={self.id!r}, "
            f"conversation_id={self.conversation_id!r}, "
            f"superseded={self.superseded_at is not None})>"
        )
