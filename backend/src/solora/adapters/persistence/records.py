"""SQLAlchemy records for the local forum."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from solora.adapters.persistence.database import Base


class ThreadRecord(Base):
    """Persisted thread metadata."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
    thread: Mapped[ThreadRecord] = relationship(back_populates="posts")
