"""Add user-managed Meshtastic connection configuration.

Revision ID: 20260908_0005
Revises: 20260908_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0005"
down_revision: str | None = "20260908_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meshtastic_connection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_type", sa.String(length=16), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("node_name", sa.String(length=64), nullable=True),
        sa.Column("firmware_version", sa.String(length=64), nullable=True),
        sa.Column("last_contact", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("meshtastic_connection")
