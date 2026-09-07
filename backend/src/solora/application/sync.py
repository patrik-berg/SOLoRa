"""Hardware-independent two-node synchronization behavior."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import blake2s

from solora.application.transport_ports import (
    InboundFrame,
    ReceiveResult,
    SyncRepository,
    TrafficPriority,
    Transport,
    TransportError,
)
from solora.domain.protocol import (
    MAX_SYNC_REFS,
    MAX_WANT_REFS,
    MessageType,
    ObjectKind,
    ObjectRef,
    PacketEnvelope,
    ProtocolError,
    decode_post_payload,
    decode_sync_payload,
    decode_sync_post_payload,
    decode_thread_payload,
    decode_want_payload,
    encode_sync_payload,
    encode_sync_post_payload,
    encode_thread_payload,
    encode_want_payload,
    new_message_id,
)

Clock = Callable[[], datetime]
IdFactory = Callable[[], bytes]


class ThreadUnavailableError(LookupError):
    """Raised when a local post targets a thread that does not exist."""


@dataclass(slots=True)
class SyncStats:
    """Local counters exposed without generating radio traffic."""

    send_attempts: int = 0
    received_posts: int = 0
    duplicate_posts: int = 0
    commit_acks: int = 0
    rejected_frames: int = 0
    received_threads: int = 0
    sync_inventories: int = 0
    want_requests: int = 0


class SyncNode:
    """Publish and receive single-frame posts over a transport port."""

    def __init__(
        self,
        repository: SyncRepository,
        transport: Transport,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory = new_message_id,
        retry_base: timedelta = timedelta(seconds=2),
        retry_max: timedelta = timedelta(minutes=2),
    ) -> None:
        self.repository = repository
        self.transport = transport
        self.clock = clock or _utc_now
        self.id_factory = id_factory
        self.retry_base = retry_base
        self.retry_max = retry_max
        self.stats = SyncStats()
        self.transport.set_receiver(self.receive)

    def publish_post(self, thread_id: int, body: str, *, destination: int) -> bytes:
        """Persist a local post and its outbound frame in one transaction."""
        thread_sync_id = self.repository.thread_sync_id(thread_id)
        if thread_sync_id is None:
            raise ThreadUnavailableError(thread_id)
        message_id = self.id_factory()
        payload = encode_sync_post_payload(thread_sync_id, body)
        frame = PacketEnvelope(MessageType.SYNC_POST, message_id, payload).encode()
        normalized_body = body.strip()
        stored = self.repository.publish_post(
            message_id=message_id,
            thread_id=thread_id,
            body=normalized_body,
            destination=destination,
            frame=frame,
            priority=TrafficPriority.USER,
            now=self.clock(),
        )
        if not stored:
            raise ThreadUnavailableError(thread_id)
        return message_id

    def request_sync(self, destination: int) -> int:
        """Queue an explicit bidirectional inventory exchange with one peer."""
        return self._queue_inventory(destination, reply_requested=True)

    def flush(self) -> int:
        """Attempt only due outbox traffic; an empty outbox is silent."""
        now = self.clock()
        entries = self.repository.due_outbox(now)
        for entry in entries:
            retry_at = now + self._retry_delay(entry.attempts)
            self.repository.record_attempt(entry.message_id, next_attempt_at=retry_at)
            self.stats.send_attempts += 1
            try:
                self.transport.send(
                    entry.destination,
                    entry.frame,
                    priority=entry.priority,
                )
            except TransportError:
                continue
        return len(entries)

    def receive(self, frame: InboundFrame) -> None:
        """Apply an inbound frame idempotently and acknowledge durable commits."""
        try:
            envelope = PacketEnvelope.decode(frame.payload)
            if envelope.message_type is MessageType.POST:
                self._receive_post(frame.source, envelope)
            elif envelope.message_type is MessageType.COMMIT_ACK:
                if self.repository.acknowledge(envelope.correlation_id, source=frame.source):
                    self.stats.commit_acks += 1
            elif envelope.message_type is MessageType.SYNC:
                self._receive_inventory(frame.source, envelope)
            elif envelope.message_type is MessageType.WANT:
                self._receive_want(frame.source, envelope)
            elif envelope.message_type is MessageType.THREAD:
                self._receive_thread(frame.source, envelope)
            elif envelope.message_type is MessageType.SYNC_POST:
                self._receive_sync_post(frame.source, envelope)
            else:
                self.stats.rejected_frames += 1
        except ProtocolError:
            self.stats.rejected_frames += 1

    def pending_count(self) -> int:
        return self.repository.pending_count()

    def _receive_post(self, source: int, envelope: PacketEnvelope) -> None:
        thread_id, body = decode_post_payload(envelope.payload)
        result = self.repository.receive_post(
            message_id=envelope.message_id,
            source=source,
            thread_id=thread_id,
            body=body,
            now=self.clock(),
        )
        if result is ReceiveResult.MISSING_THREAD:
            return
        if result is ReceiveResult.STORED:
            self.stats.received_posts += 1
        else:
            self.stats.duplicate_posts += 1

        acknowledgement = PacketEnvelope(
            MessageType.COMMIT_ACK, self.id_factory(), correlation_id=envelope.message_id
        ).encode()
        self._send_ack(source, acknowledgement)

    def _receive_inventory(self, source: int, envelope: PacketEnvelope) -> None:
        reply_requested, advertised = decode_sync_payload(envelope.payload)
        if not self.repository.has_received(envelope.message_id):
            self.stats.sync_inventories += 1
            missing = tuple(self.repository.missing_objects(advertised))
            self._queue_wants(source, missing)
            if reply_requested:
                self._queue_inventory(
                    source,
                    reply_requested=False,
                    response_to=envelope.message_id,
                )
            self.repository.record_control_message(
                message_id=envelope.message_id,
                source=source,
                message_type=int(MessageType.SYNC),
                now=self.clock(),
            )
        self._acknowledge(source, envelope.message_id)

    def _receive_want(self, source: int, envelope: PacketEnvelope) -> None:
        requested = decode_want_payload(envelope.payload)
        if not self.repository.has_received(envelope.message_id):
            if not all(self._queue_object(source, ref) for ref in requested):
                return
            self.stats.want_requests += 1
            self.repository.record_control_message(
                message_id=envelope.message_id,
                source=source,
                message_type=int(MessageType.WANT),
                now=self.clock(),
            )
        self._acknowledge(source, envelope.message_id)

    def _receive_thread(self, source: int, envelope: PacketEnvelope) -> None:
        title = decode_thread_payload(envelope.payload)
        result = self.repository.receive_thread(
            sync_id=envelope.message_id,
            source=source,
            title=title,
            now=self.clock(),
        )
        if result is ReceiveResult.STORED:
            self.stats.received_threads += 1
        self.repository.resolve_repair(ObjectRef(ObjectKind.THREAD, envelope.message_id))
        self._acknowledge(source, envelope.message_id)

    def _receive_sync_post(self, source: int, envelope: PacketEnvelope) -> None:
        thread_sync_id, body = decode_sync_post_payload(envelope.payload)
        result = self.repository.receive_sync_post(
            message_id=envelope.message_id,
            source=source,
            thread_sync_id=thread_sync_id,
            body=body,
            now=self.clock(),
        )
        if result is ReceiveResult.MISSING_THREAD:
            self._queue_wants(
                source,
                (ObjectRef(ObjectKind.THREAD, thread_sync_id),),
            )
            return
        if result is ReceiveResult.STORED:
            self.stats.received_posts += 1
        else:
            self.stats.duplicate_posts += 1
        self.repository.resolve_repair(ObjectRef(ObjectKind.POST, envelope.message_id))
        self._acknowledge(source, envelope.message_id)

    def _queue_inventory(
        self,
        destination: int,
        *,
        reply_requested: bool,
        response_to: bytes | None = None,
    ) -> int:
        refs = self.repository.known_objects()
        pages = [
            tuple(refs[index : index + MAX_SYNC_REFS])
            for index in range(0, len(refs), MAX_SYNC_REFS)
        ] or [()]
        queued = 0
        for index, page in enumerate(pages):
            message_id = (
                self._response_id(response_to, index)
                if response_to is not None
                else self.id_factory()
            )
            payload = encode_sync_payload(
                page,
                reply_requested=reply_requested and index == 0,
            )
            frame = PacketEnvelope(MessageType.SYNC, message_id, payload).encode()
            if self.repository.queue_frame(
                message_id=message_id,
                destination=destination,
                frame=frame,
                priority=TrafficPriority.BACKGROUND,
                now=self.clock(),
            ):
                queued += 1
        return queued

    def _queue_wants(self, destination: int, refs: tuple[ObjectRef, ...]) -> int:
        unrequested = self.repository.unrequested_objects(refs, destination=destination)
        queued = 0
        for index in range(0, len(unrequested), MAX_WANT_REFS):
            page = tuple(unrequested[index : index + MAX_WANT_REFS])
            message_id = self.id_factory()
            frame = PacketEnvelope(
                MessageType.WANT,
                message_id,
                encode_want_payload(page),
            ).encode()
            if self.repository.queue_want(
                refs=page,
                message_id=message_id,
                destination=destination,
                frame=frame,
                now=self.clock(),
            ):
                queued += 1
        return queued

    def _queue_object(self, destination: int, ref: ObjectRef) -> bool:
        item = self.repository.get_sync_object(ref)
        if item is None:
            return False
        if ref.kind is ObjectKind.THREAD:
            message_type = MessageType.THREAD
            payload = encode_thread_payload(item.content)
        else:
            if item.thread_sync_id is None:
                return False
            message_type = MessageType.SYNC_POST
            payload = encode_sync_post_payload(item.thread_sync_id, item.content)
        frame = PacketEnvelope(message_type, ref.object_id, payload).encode()
        self.repository.queue_frame(
            message_id=ref.object_id,
            destination=destination,
            frame=frame,
            priority=TrafficPriority.BACKGROUND,
            now=self.clock(),
        )
        return True

    def _acknowledge(self, destination: int, correlation_id: bytes) -> None:
        acknowledgement = PacketEnvelope(
            MessageType.COMMIT_ACK,
            self.id_factory(),
            correlation_id=correlation_id,
        ).encode()
        self._send_ack(destination, acknowledgement)

    def _send_ack(self, destination: int, acknowledgement: bytes) -> None:
        try:
            self.transport.send(
                destination,
                acknowledgement,
                priority=TrafficPriority.USER,
            )
        except TransportError:
            # The sender retains its durable frame and will retry it.
            return

    @staticmethod
    def _response_id(request_id: bytes, page: int) -> bytes:
        return blake2s(
            b"solora-sync-response" + request_id + page.to_bytes(2),
            digest_size=12,
        ).digest()

    def _retry_delay(self, previous_attempts: int) -> timedelta:
        multiplier = 2 ** min(previous_attempts, 16)
        delay = self.retry_base * multiplier
        return delay if delay < self.retry_max else self.retry_max


def _utc_now() -> datetime:
    # SQLite stores these scheduling timestamps without a timezone offset.
    return datetime.now(UTC).replace(tzinfo=None)
