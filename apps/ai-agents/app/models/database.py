"""SQLAlchemy models for the AI Agents service.

Defines the database schema using SQLAlchemy 2.0 declarative style
with async support. Uses pgvector for vector similarity search.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
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


class ConversationSummaryModel(Base):
    """SQLAlchemy model for conversation summaries (future use).

    Stores summarized conversation data for medium-term memory.
    This model is a placeholder for the conversation summarization
    feature planned for a future iteration.

    Attributes:
        id: UUID primary key.
        user_id: Foreign reference to the user.
        conversation_id: Reference to the conversation (from api-backend).
        summary: Summarized text of the conversation.
        message_count: Number of messages summarized.
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<ConversationSummaryModel(id={self.id!r}, "
            f"conversation_id={self.conversation_id!r})>"
        )
