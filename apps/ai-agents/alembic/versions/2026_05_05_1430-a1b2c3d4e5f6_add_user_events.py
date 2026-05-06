"""add user_events table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-05 14:30:00.000000

First migration in this project. The pre-existing ``insights`` and
``conversation_summaries`` tables are bootstrapped by
``Base.metadata.create_all`` in ``app/main.py`` and are intentionally
NOT included here — alembic autogenerate would have tried to create
them, conflicting with running deployments. This migration only
introduces the new ``user_events`` table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "occurs_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "occurs_at_has_time",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="conversation",
        ),
        sa.Column("source_message_id", sa.String(length=36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("timezone", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_events_user_id",
        "user_events",
        ["user_id"],
    )
    op.create_index(
        "ix_user_events_occurs_at",
        "user_events",
        ["occurs_at"],
    )
    op.create_index(
        "ix_user_events_source_message_id",
        "user_events",
        ["source_message_id"],
    )
    op.create_index(
        "ix_user_events_user_occurs",
        "user_events",
        ["user_id", "occurs_at"],
    )
    op.create_index(
        "ix_user_events_user_status",
        "user_events",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_events_user_status", table_name="user_events")
    op.drop_index("ix_user_events_user_occurs", table_name="user_events")
    op.drop_index(
        "ix_user_events_source_message_id",
        table_name="user_events",
    )
    op.drop_index("ix_user_events_occurs_at", table_name="user_events")
    op.drop_index("ix_user_events_user_id", table_name="user_events")
    op.drop_table("user_events")
