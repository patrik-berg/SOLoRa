"""Add message IDs, durable outbox, and receive deduplication.

Revision ID: 20260907_0002
Revises: 20260907_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0002"
down_revision: str | None = "20260907_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("message_id", sa.LargeBinary(length=12), nullable=True))
    op.execute("UPDATE posts SET message_id = randomblob(12) WHERE message_id IS NULL")
    op.create_index("ux_posts_message_id", "posts", ["message_id"], unique=True)

    op.create_table(
        "outbox",
        sa.Column("message_id", sa.LargeBinary(length=12), primary_key=True),
        sa.Column("destination", sa.Integer(), nullable=False),
        sa.Column("frame", sa.LargeBinary(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_outbox_due",
        "outbox",
        ["priority", "next_attempt_at", "created_at"],
    )
    op.create_table(
        "received_messages",
        sa.Column("message_id", sa.LargeBinary(length=12), primary_key=True),
        sa.Column("source_node", sa.Integer(), nullable=False),
        sa.Column("message_type", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("received_messages")
    op.drop_index("ix_outbox_due", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ux_posts_message_id", table_name="posts")
    op.drop_column("posts", "message_id")
