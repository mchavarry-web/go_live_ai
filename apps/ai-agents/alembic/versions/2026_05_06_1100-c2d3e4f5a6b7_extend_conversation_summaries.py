"""extend conversation_summaries for Phase 12

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-06 11:00:00.000000

The base ``conversation_summaries`` table is bootstrapped by
``Base.metadata.create_all`` in ``app/main.py`` (same pattern as
``insights``). This migration adds the four columns Phase 13 needs to
do range-aware history truncation, plus a partial index on the latest
non-superseded summary per conversation.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversation_summaries",
        sa.Column(
            "summary_token_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "conversation_summaries",
        sa.Column("range_start_message_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "conversation_summaries",
        sa.Column("range_end_message_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "conversation_summaries",
        sa.Column(
            "superseded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conv_summaries_range_end",
        "conversation_summaries",
        ["range_end_message_id"],
    )
    op.create_index(
        "ix_conv_summaries_conv_latest",
        "conversation_summaries",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conv_summaries_conv_latest", table_name="conversation_summaries")
    op.drop_index("ix_conv_summaries_range_end", table_name="conversation_summaries")
    op.drop_column("conversation_summaries", "superseded_at")
    op.drop_column("conversation_summaries", "range_end_message_id")
    op.drop_column("conversation_summaries", "range_start_message_id")
    op.drop_column("conversation_summaries", "summary_token_count")
