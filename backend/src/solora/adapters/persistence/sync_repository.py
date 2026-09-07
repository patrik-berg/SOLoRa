"""SQLite-backed durable outbox and receive deduplication."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from solora.adapters.persistence.records import (
    OutboxRecord,
    PostRecord,
    ReceivedMessageRecord,
    ThreadRecord,
)
from solora.application.transport_ports import (
    OutboxEntry,
    ReceiveResult,
    TrafficPriority,
)
from solora.domain.protocol import MessageType


class SqlAlchemySyncRepository:
    """Apply synchronization state changes transactionally."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def publish_post(
        self,
        *,
        message_id: bytes,
        thread_id: int,
        body: str,
        destination: int,
        frame: bytes,
        priority: TrafficPriority,
        now: datetime,
    ) -> bool:
        if self.session.get(ThreadRecord, thread_id) is None:
            return False
        self.session.add(PostRecord(thread_id=thread_id, message_id=message_id, body=body))
        self.session.add(
            OutboxRecord(
                message_id=message_id,
                destination=destination,
                frame=frame,
                priority=int(priority),
                attempts=0,
                next_attempt_at=now,
                created_at=now,
            )
        )
        self.session.commit()
        return True

    def due_outbox(self, now: datetime) -> list[OutboxEntry]:
        statement = (
            select(OutboxRecord)
            .where(OutboxRecord.next_attempt_at <= now)
            .order_by(
                OutboxRecord.priority.desc(), OutboxRecord.created_at, OutboxRecord.message_id
            )
        )
        records = self.session.scalars(statement).all()
        return [
            OutboxEntry(
                message_id=record.message_id,
                destination=record.destination,
                frame=record.frame,
                priority=TrafficPriority(record.priority),
                attempts=record.attempts,
                next_attempt_at=record.next_attempt_at,
            )
            for record in records
        ]

    def record_attempt(self, message_id: bytes, *, next_attempt_at: datetime) -> None:
        self.session.execute(
            update(OutboxRecord)
            .where(OutboxRecord.message_id == message_id)
            .values(
                attempts=OutboxRecord.attempts + 1,
                next_attempt_at=next_attempt_at,
            )
        )
        self.session.commit()

    def acknowledge(self, message_id: bytes, *, source: int) -> bool:
        record = self.session.scalar(
            select(OutboxRecord).where(
                OutboxRecord.message_id == message_id,
                OutboxRecord.destination == source,
            )
        )
        if record is None:
            return False
        self.session.delete(record)
        self.session.commit()
        return True

    def receive_post(
        self,
        *,
        message_id: bytes,
        source: int,
        thread_id: int,
        body: str,
        now: datetime,
    ) -> ReceiveResult:
        if self.session.get(ReceivedMessageRecord, message_id) is not None:
            return ReceiveResult.DUPLICATE
        if self.session.get(ThreadRecord, thread_id) is None:
            return ReceiveResult.MISSING_THREAD

        existing_post = self.session.scalar(
            select(PostRecord).where(PostRecord.message_id == message_id)
        )
        self.session.add(
            ReceivedMessageRecord(
                message_id=message_id,
                source_node=source,
                message_type=int(MessageType.POST),
                received_at=now,
            )
        )
        if existing_post is None:
            self.session.add(PostRecord(thread_id=thread_id, message_id=message_id, body=body))
            result = ReceiveResult.STORED
        else:
            result = ReceiveResult.DUPLICATE
        self.session.commit()
        return result

    def pending_count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(OutboxRecord)) or 0
