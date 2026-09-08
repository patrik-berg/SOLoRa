"""Bounded, passive diagnostics. No transport calls, persistence, or UI dependency."""

from collections import deque
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from solora.domain.protocol import (
    MESHTASTIC_DATA_PAYLOAD_MAX,
    PROTOCOL_VERSION,
    MessageType,
    PacketEnvelope,
    decode_post_payload,
    decode_sync_payload,
    decode_sync_post_payload,
    decode_thread_payload,
    decode_want_payload,
)

# Fail closed: adding a wire type does NOT automatically make its bytes public.
# AUTH 12/13 and all unknown versions/types stay hidden, including IDs.
PUBLIC_DIAGNOSTIC_TYPES = frozenset({1, 2, 3, 4, 5, 6})


class TrafficSnapshot(TypedDict):
    session: str
    revision: int
    capacity: int
    oldest: int
    registry: list[dict[str, Any]]
    events: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TrafficObservation:
    direction: Literal["TX", "RX"]
    source: int
    destination: int
    payload: bytes
    channel_name: str | None = None
    channel_index: int | None = None
    portnum: int | None = None
    transport: str = "meshtastic"
    status: str = "Received"
    packet_id: int | None = None


class TrafficSink(Protocol):
    def capture(self, observation: TrafficObservation) -> None: ...


def observe(sink: TrafficSink | None, observation: TrafficObservation) -> None:
    """Diagnostics failures must never change send/receive behavior."""
    if sink is not None:
        with suppress(Exception):
            sink.capture(observation)


@dataclass(frozen=True, slots=True)
class TrafficEvent:
    sequence: int
    timestamp: str
    observation: TrafficObservation
    payload_size: int
    redacted: bool


class TrafficBuffer:
    """Nonblocking capture; decode only on the HTTP/read side, outside the lock."""

    def __init__(self, capacity: int = 1000) -> None:
        if not 1 <= capacity <= 10000:
            raise ValueError("Traffic capacity must be between 1 and 10000")
        self.capacity = capacity
        self.session = uuid4().hex
        self._events: deque[TrafficEvent] = deque(maxlen=capacity)
        self._revision = 0
        self._lock = Lock()

    def capture(self, observation: TrafficObservation) -> None:
        raw = observation.payload
        public = (
            bool(raw)
            and raw[0] >> 4 == PROTOCOL_VERSION
            and (raw[0] & 15 in PUBLIC_DIAGNOSTIC_TYPES)
            and len(raw) <= MESHTASTIC_DATA_PAYLOAD_MAX
        )
        # Sanitize before retention; never retain opaque SDK packet/config objects.
        safe = TrafficObservation(
            observation.direction,
            observation.source,
            observation.destination,
            bytes(raw) if public else b"",
            observation.channel_name,
            observation.channel_index,
            observation.portnum,
            observation.transport,
            observation.status,
            observation.packet_id,
        )
        if not self._lock.acquire(blocking=False):
            return  # diagnostics may drop on contention; protocol must never wait
        try:
            self._revision += 1
            self._events.append(
                TrafficEvent(
                    self._revision,
                    datetime.now(UTC).isoformat(),
                    safe,
                    len(raw),
                    not public,
                )
            )
        finally:
            self._lock.release()

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._revision += 1

    def snapshot(self, after: int = 0) -> TrafficSnapshot:
        with self._lock:
            events = tuple(self._events)
            revision = self._revision
        return {
            "session": self.session,
            "revision": revision,
            "capacity": self.capacity,
            "oldest": events[0].sequence if events else revision + 1,
            "registry": [
                {
                    "value": int(kind),
                    "name": kind.name,
                    "sensitive": int(kind) not in PUBLIC_DIAGNOSTIC_TYPES,
                }
                for kind in MessageType
            ],
            "events": [present(event) for event in events if event.sequence > after],
        }


def present(event: TrafficEvent) -> dict[str, Any]:
    observation = event.observation
    result = asdict(observation)
    result.pop("payload")
    result.update(
        sequence=event.sequence,
        timestamp=event.timestamp,
        payload_size=event.payload_size,
        raw_hex=None,
        message_type="UNKNOWN",
        message_id=None,
        correlation_id=None,
        protocol_version=None,
        decode_state="hidden",
        parsed_fields={},
        decoded="",
        decode_error=None,
        redacted=event.redacted,
    )
    if event.redacted:
        result["decoded"] = "Payload hidden: sensitive or unreviewed message type/version"
        return result
    raw = observation.payload
    result["raw_hex"] = raw.hex()
    result["protocol_version"] = raw[0] >> 4
    result["message_type"] = MessageType(raw[0] & 15).name
    try:
        envelope = PacketEnvelope.decode(raw)
        result["message_id"] = envelope.message_id.hex()
        result["correlation_id"] = envelope.correlation_id.hex()
        fields: dict[str, object] = {"payload_bytes": len(envelope.payload)}
        kind = envelope.message_type
        if kind is MessageType.POST:
            thread, body = decode_post_payload(envelope.payload)
            fields.update(thread_local_id=thread, body=body)
        elif kind is MessageType.THREAD:
            fields["title"] = decode_thread_payload(envelope.payload)
        elif kind is MessageType.SYNC_POST:
            thread_id, body = decode_sync_post_payload(envelope.payload)
            fields.update(thread_id=thread_id.hex(), body=body)
        elif kind in (MessageType.WANT, MessageType.SYNC):
            if kind is MessageType.SYNC:
                reply, refs = decode_sync_payload(envelope.payload)
                fields["reply_requested"] = reply
            else:
                refs = decode_want_payload(envelope.payload)
            fields["objects"] = [{"kind": ref.kind.name, "id": ref.object_id.hex()} for ref in refs]
        else:
            fields["application"] = "COMMIT_ACK observed; not a Meshtastic routing ACK"
        result["parsed_fields"] = fields
        result["decoded"] = fields
        result["decode_state"] = "decoded"
    except Exception:
        # Never expose exception repr: future parsers might include secret bytes.
        result["decode_state"] = "error"
        result["decode_error"] = "Malformed SOLoRa envelope or payload"
    return result
