"""SQLAlchemy records for the local forum."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from solora.adapters.persistence.database import Base


class ThreadRecord(Base):
    """Persisted thread metadata."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_id: Mapped[bytes | None] = mapped_column(LargeBinary(12))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
    posts: Mapped[list["PostRecord"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="PostRecord.id",
    )


class PostRecord(Base):
    """Persisted post content."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"))
    message_id: Mapped[bytes | None] = mapped_column(LargeBinary(12))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
    thread: Mapped[ThreadRecord] = relationship(back_populates="posts")


Index("ux_threads_sync_id", ThreadRecord.sync_id, unique=True)
Index("ux_posts_message_id", PostRecord.message_id, unique=True)


class OutboxRecord(Base):
    """Persisted user data awaiting SOLoRa commit acknowledgement."""

    __tablename__ = "outbox"

    message_id: Mapped[bytes] = mapped_column(LargeBinary(12), primary_key=True)
    destination: Mapped[int] = mapped_column(Integer)
    frame: Mapped[bytes] = mapped_column(LargeBinary)
    priority: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ReceivedMessageRecord(Base):
    """Application IDs already applied to local persistent state."""

    __tablename__ = "received_messages"

    message_id: Mapped[bytes] = mapped_column(LargeBinary(12), primary_key=True)
    source_node: Mapped[int] = mapped_column(Integer)
    message_type: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime)


class RepairRequestRecord(Base):
    """A missing object already requested from one peer."""

    __tablename__ = "repair_requests"

    destination: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_kind: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_id: Mapped[bytes] = mapped_column(LargeBinary(12), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime)
