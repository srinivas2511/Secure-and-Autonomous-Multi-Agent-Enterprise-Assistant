"""Add system_settings table for persistent runtime configuration.

Revision ID: 001
Revises:
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Seed the default HITL threshold so the app works without a manual insert.
    op.execute(
        "INSERT INTO system_settings (key, value) "
        "VALUES ('hitl_confidence_threshold', '0.5') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("system_settings")
