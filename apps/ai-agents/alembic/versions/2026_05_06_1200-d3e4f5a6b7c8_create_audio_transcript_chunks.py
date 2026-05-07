"""create audio_transcript_chunks for Phase 14

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-06 12:00:00.000000

Adds the embedded transcript-chunk pool. The model is also bootstrapped
by ``Base.metadata.create_all``; this migration formalises the schema for
production deploys.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audio_transcript_chunks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("audio_chunk_id", sa.String(length=36), nullable=False),
        sa.Column("audio_session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_in_chunk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        # NB: pgvector column added below via raw SQL — alembic does not
        # natively know about Vector(...). The runtime model in
        # database.py does the SQLAlchemy-side binding.
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute("ALTER TABLE audio_transcript_chunks ADD COLUMN embedding vector(1536)")
    op.create_index("ix_audio_transcript_chunks_user_id", "audio_transcript_chunks", ["user_id"])
    op.create_index(
        "ix_audio_transcript_chunks_audio_chunk_id",
        "audio_transcript_chunks",
        ["audio_chunk_id"],
    )
    op.create_index(
        "ix_audio_transcript_chunks_audio_session_id",
        "audio_transcript_chunks",
        ["audio_session_id"],
    )
    op.create_index(
        "ix_audio_chunks_user_recorded",
        "audio_transcript_chunks",
        ["user_id", "recorded_at"],
    )
    op.execute(
        "CREATE INDEX ix_audio_chunks_embedding_ivfflat "
        "ON audio_transcript_chunks USING ivfflat (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audio_chunks_embedding_ivfflat")
    op.drop_index("ix_audio_chunks_user_recorded", table_name="audio_transcript_chunks")
    op.drop_index(
        "ix_audio_transcript_chunks_audio_session_id",
        table_name="audio_transcript_chunks",
    )
    op.drop_index(
        "ix_audio_transcript_chunks_audio_chunk_id",
        table_name="audio_transcript_chunks",
    )
    op.drop_index(
        "ix_audio_transcript_chunks_user_id",
        table_name="audio_transcript_chunks",
    )
    op.drop_table("audio_transcript_chunks")
