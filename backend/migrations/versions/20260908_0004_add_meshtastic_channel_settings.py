"""Add local Meshtastic channel selection.

Revision ID: 20260908_0004
Revises: 20260907_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0004"
down_revision: str | None = "20260907_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meshtastic_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("selected_node_id", sa.Integer(), nullable=False),
        sa.Column("selected_channel_index", sa.Integer(), nullable=False),
        sa.Column("selected_channel_name", sa.String(length=12), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("meshtastic_settings")
