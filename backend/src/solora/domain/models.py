"""Framework-independent forum entities."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Post:
    """A locally persisted forum post."""

    id: int
    thread_id: int
    body: str
    created_at: datetime
    message_id: str | None = None


@dataclass(frozen=True, slots=True)
class Thread:
    """A forum thread and, when requested, its posts."""

    id: int
    title: str
    created_at: datetime
    post_count: int = 0
    posts: tuple[Post, ...] = field(default_factory=tuple)
    sync_id: str | None = None
