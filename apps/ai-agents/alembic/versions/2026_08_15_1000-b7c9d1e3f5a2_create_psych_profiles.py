"""create psych_profiles for DEV-98 (Humantic AI + Sentino profiling)

Revision ID: b7c9d1e3f5a2
Revises: f5a6b7c8d9e0
Create Date: 2026-08-15 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "b7c9d1e3f5a2"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "psych_profiles",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("traits", JSONB(), nullable=False),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column("source_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_psych_profiles_user_id",
        "psych_profiles",
        ["user_id"],
    )
    op.create_index(
        "ix_psych_profiles_user_provider",
        "psych_profiles",
        ["user_id", "provider"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_psych_profiles_user_provider",
        table_name="psych_profiles",
    )
    op.drop_index(
        "ix_psych_profiles_user_id",
        table_name="psych_profiles",
    )
    op.drop_table("psych_profiles")
