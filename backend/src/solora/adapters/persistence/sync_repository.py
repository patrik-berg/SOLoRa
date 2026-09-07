"""SQLite-backed durable outbox and receive deduplication."""

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from solora.adapters.persistence.records import (
    OutboxRecord,
    PostRecord,
    ReceivedMessageRecord,
    RepairRequestRecord,
    ThreadRecord,
)
from solora.application.transport_ports import (
    OutboxEntry,
    ReceiveResult,
    SyncObject,
    TrafficPriority,
)
from solora.domain.protocol import MessageType, ObjectKind, ObjectRef


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

    def thread_sync_id(self, thread_id: int) -> bytes | None:
        record = self.session.get(ThreadRecord, thread_id)
        return record.sync_id if record is not None else None

    def queue_frame(
        self,
        *,
        message_id: bytes,
        destination: int,
        frame: bytes,
        priority: TrafficPriority,
        now: datetime,
    ) -> bool:
        if self.session.get(OutboxRecord, message_id) is not None:
            return False
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

    def receive_thread(
        self,
        *,
        sync_id: bytes,
        source: int,
        title: str,
        now: datetime,
    ) -> ReceiveResult:
        if self.session.get(ReceivedMessageRecord, sync_id) is not None:
            return ReceiveResult.DUPLICATE
        existing = self.session.scalar(select(ThreadRecord).where(ThreadRecord.sync_id == sync_id))
        self.session.add(
            ReceivedMessageRecord(
                message_id=sync_id,
                source_node=source,
                message_type=int(MessageType.THREAD),
                received_at=now,
            )
        )
        if existing is None:
            self.session.add(ThreadRecord(sync_id=sync_id, title=title))
            result = ReceiveResult.STORED
        else:
            result = ReceiveResult.DUPLICATE
        self.session.commit()
        return result

    def receive_sync_post(
        self,
        *,
        message_id: bytes,
        source: int,
        thread_sync_id: bytes,
        body: str,
        now: datetime,
    ) -> ReceiveResult:
        if self.session.get(ReceivedMessageRecord, message_id) is not None:
            return ReceiveResult.DUPLICATE
        thread = self.session.scalar(
            select(ThreadRecord).where(ThreadRecord.sync_id == thread_sync_id)
        )
        if thread is None:
            return ReceiveResult.MISSING_THREAD

        existing = self.session.scalar(
            select(PostRecord).where(PostRecord.message_id == message_id)
        )
        self.session.add(
            ReceivedMessageRecord(
                message_id=message_id,
                source_node=source,
                message_type=int(MessageType.SYNC_POST),
                received_at=now,
            )
        )
        if existing is None:
            self.session.add(PostRecord(thread_id=thread.id, message_id=message_id, body=body))
            result = ReceiveResult.STORED
        else:
            result = ReceiveResult.DUPLICATE
        self.session.commit()
        return result

    def record_control_message(
        self,
        *,
        message_id: bytes,
        source: int,
        message_type: int,
        now: datetime,
    ) -> bool:
        if self.session.get(ReceivedMessageRecord, message_id) is not None:
            return False
        self.session.add(
            ReceivedMessageRecord(
                message_id=message_id,
                source_node=source,
                message_type=message_type,
                received_at=now,
            )
        )
        self.session.commit()
        return True

    def has_received(self, message_id: bytes) -> bool:
        return self.session.get(ReceivedMessageRecord, message_id) is not None

    def known_objects(self) -> list[ObjectRef]:
        thread_ids = self.session.scalars(
            select(ThreadRecord.sync_id)
            .where(ThreadRecord.sync_id.is_not(None))
            .order_by(ThreadRecord.sync_id)
        ).all()
        post_ids = self.session.scalars(
            select(PostRecord.message_id)
            .where(PostRecord.message_id.is_not(None))
            .order_by(PostRecord.message_id)
        ).all()
        return [ObjectRef(ObjectKind.THREAD, item) for item in thread_ids if item is not None] + [
            ObjectRef(ObjectKind.POST, item) for item in post_ids if item is not None
        ]

    def missing_objects(self, refs: tuple[ObjectRef, ...]) -> list[ObjectRef]:
        missing: list[ObjectRef] = []
        for ref in refs:
            model = ThreadRecord if ref.kind is ObjectKind.THREAD else PostRecord
            column = (
                ThreadRecord.sync_id if ref.kind is ObjectKind.THREAD else PostRecord.message_id
            )
            if self.session.scalar(select(model).where(column == ref.object_id)) is None:
                missing.append(ref)
        return missing

    def get_sync_object(self, ref: ObjectRef) -> SyncObject | None:
        if ref.kind is ObjectKind.THREAD:
            thread = self.session.scalar(
                select(ThreadRecord).where(ThreadRecord.sync_id == ref.object_id)
            )
            return SyncObject(ref, thread.title) if thread is not None else None

        post = self.session.scalar(select(PostRecord).where(PostRecord.message_id == ref.object_id))
        if post is None:
            return None
        thread = self.session.get(ThreadRecord, post.thread_id)
        if thread is None or thread.sync_id is None:
            return None
        return SyncObject(ref, post.body, thread.sync_id)

    def queue_want(
        self,
        *,
        refs: tuple[ObjectRef, ...],
        message_id: bytes,
        destination: int,
        frame: bytes,
        now: datetime,
    ) -> bool:
        if not refs or self.session.get(OutboxRecord, message_id) is not None:
            return False
        for ref in refs:
            key = (destination, int(ref.kind), ref.object_id)
            if self.session.get(RepairRequestRecord, key) is not None:
                return False
        self.session.add_all(
            [
                RepairRequestRecord(
                    destination=destination,
                    object_kind=int(ref.kind),
                    object_id=ref.object_id,
                    requested_at=now,
                )
                for ref in refs
            ]
        )
        self.session.add(
            OutboxRecord(
                message_id=message_id,
                destination=destination,
                frame=frame,
                priority=int(TrafficPriority.BACKGROUND),
                attempts=0,
                next_attempt_at=now,
                created_at=now,
            )
        )
        self.session.commit()
        return True

    def unrequested_objects(
        self,
        refs: tuple[ObjectRef, ...],
        *,
        destination: int,
    ) -> list[ObjectRef]:
        return [
            ref
            for ref in refs
            if self.session.get(
                RepairRequestRecord,
                (destination, int(ref.kind), ref.object_id),
            )
            is None
        ]

    def resolve_repair(self, ref: ObjectRef) -> None:
        self.session.execute(
            delete(RepairRequestRecord).where(
                RepairRequestRecord.object_kind == int(ref.kind),
                RepairRequestRecord.object_id == ref.object_id,
            )
        )
        self.session.commit()

    def pending_count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(OutboxRecord)) or 0
