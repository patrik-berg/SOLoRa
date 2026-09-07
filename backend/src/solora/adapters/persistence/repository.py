"""SQLite-backed forum repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from solora.adapters.persistence.records import PostRecord, ThreadRecord
from solora.domain.models import Post, Thread
from solora.domain.protocol import message_id_hex, new_message_id


def _post_entity(record: PostRecord) -> Post:
    return Post(
        id=record.id,
        thread_id=record.thread_id,
        body=record.body,
        created_at=record.created_at,
        message_id=message_id_hex(record.message_id) if record.message_id is not None else None,
    )


def _thread_entity(record: ThreadRecord, *, include_posts: bool) -> Thread:
    posts = tuple(_post_entity(post) for post in record.posts) if include_posts else ()
    return Thread(
        id=record.id,
        title=record.title,
        created_at=record.created_at,
        sync_id=message_id_hex(record.sync_id) if record.sync_id is not None else None,
        post_count=len(record.posts),
        posts=posts,
    )


class SqlAlchemyForumRepository:
    """Persist forum data in the current SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_threads(self) -> list[Thread]:
        statement = (
            select(ThreadRecord)
            .options(selectinload(ThreadRecord.posts))
            .order_by(ThreadRecord.id.desc())
            .execution_options(populate_existing=True)
        )
        records = self.session.scalars(statement).all()
        return [_thread_entity(record, include_posts=False) for record in records]

    def get_thread(self, thread_id: int) -> Thread | None:
        statement = (
            select(ThreadRecord)
            .where(ThreadRecord.id == thread_id)
            .options(selectinload(ThreadRecord.posts))
            .execution_options(populate_existing=True)
        )
        record = self.session.scalar(statement)
        return _thread_entity(record, include_posts=True) if record else None

    def create_thread(self, title: str) -> Thread:
        record = ThreadRecord(sync_id=new_message_id(), title=title)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return _thread_entity(record, include_posts=False)

    def create_post(self, thread_id: int, body: str) -> Post | None:
        if self.session.get(ThreadRecord, thread_id) is None:
            return None

        record = PostRecord(thread_id=thread_id, message_id=new_message_id(), body=body)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return _post_entity(record)
