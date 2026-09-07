"""Hardware-independent two-node synchronization behavior."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from solora.application.transport_ports import (
    InboundFrame,
    ReceiveResult,
    SyncRepository,
    TrafficPriority,
    Transport,
    TransportError,
)
from solora.domain.protocol import (
    MessageType,
    PacketEnvelope,
    ProtocolError,
    decode_post_payload,
    encode_post_payload,
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
        message_id = self.id_factory()
        payload = encode_post_payload(thread_id, body)
        frame = PacketEnvelope(MessageType.POST, message_id, payload).encode()
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
            MessageType.COMMIT_ACK,
            self.id_factory(),
            correlation_id=envelope.message_id,
        ).encode()
        self.transport.send(source, acknowledgement, priority=TrafficPriority.USER)

    def _retry_delay(self, previous_attempts: int) -> timedelta:
        multiplier = 2 ** min(previous_attempts, 16)
        delay = self.retry_base * multiplier
        return delay if delay < self.retry_max else self.retry_max


def _utc_now() -> datetime:
    # SQLite stores these scheduling timestamps without a timezone offset.
    return datetime.now(UTC).replace(tzinfo=None)
