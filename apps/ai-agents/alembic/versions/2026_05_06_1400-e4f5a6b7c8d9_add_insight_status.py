"""add insight status / superseded_at / superseded_by_id

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-06 14:00:00.000000

Wave B.1 — supports correction/contradiction handling. Existing rows
are stamped 'active' by the column default. New CorrectionDetectorChain
sets 'superseded' on rows that the user has retracted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "insights",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "insights",
        sa.Column("superseded_by_id", UUID(as_uuid=False), nullable=True),
    )
    op.create_index(
        "ix_insights_user_status",
        "insights",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_insights_user_status", table_name="insights")
    op.drop_column("insights", "superseded_by_id")
    op.drop_column("insights", "superseded_at")
    op.drop_column("insights", "status")
