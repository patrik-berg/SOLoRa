"""Add global thread IDs and persistent repair request state.

Revision ID: 20260907_0003
Revises: 20260907_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0003"
down_revision: str | None = "20260907_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("sync_id", sa.LargeBinary(length=12), nullable=True))
    op.execute("UPDATE threads SET sync_id = randomblob(12) WHERE sync_id IS NULL")
    op.create_index("ux_threads_sync_id", "threads", ["sync_id"], unique=True)
    op.create_table(
        "repair_requests",
        sa.Column("destination", sa.Integer(), nullable=False),
        sa.Column("object_kind", sa.Integer(), nullable=False),
        sa.Column("object_id", sa.LargeBinary(length=12), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("destination", "object_kind", "object_id"),
    )


def downgrade() -> None:
    op.drop_table("repair_requests")
    op.drop_index("ux_threads_sync_id", table_name="threads")
    op.drop_column("threads", "sync_id")
