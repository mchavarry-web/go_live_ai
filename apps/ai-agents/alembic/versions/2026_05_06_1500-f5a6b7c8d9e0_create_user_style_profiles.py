"""create user_style_profiles for Wave B.3

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-05-06 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_style_profiles",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("primary_language", sa.String(length=8), nullable=True),
        sa.Column("dialect", sa.String(length=40), nullable=True),
        sa.Column("formality_level", sa.Float(), nullable=True),
        sa.Column("emoji_frequency", sa.String(length=16), nullable=True),
        sa.Column("custom_expressions", sa.JSON(), nullable=True),
        sa.Column("sentence_length_avg", sa.Float(), nullable=True),
        sa.Column("common_greetings", sa.JSON(), nullable=True),
        sa.Column("common_closings", sa.JSON(), nullable=True),
        sa.Column("fillers", sa.JSON(), nullable=True),
        sa.Column("slang_observed", sa.JSON(), nullable=True),
        sa.Column("punctuation_habits", sa.JSON(), nullable=True),
        sa.Column("humor_style", sa.String(length=40), nullable=True),
        sa.Column("directness", sa.Float(), nullable=True),
        sa.Column("verbosity", sa.Float(), nullable=True),
        sa.Column("never_says", sa.JSON(), nullable=True),
        sa.Column("example_phrases", sa.JSON(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_user_style_profiles_user_id",
        "user_style_profiles",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_style_profiles_user_id",
        table_name="user_style_profiles",
    )
    op.drop_table("user_style_profiles")
