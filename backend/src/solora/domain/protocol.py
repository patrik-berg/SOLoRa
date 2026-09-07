"""Versioned binary messages carried inside Meshtastic ``Data.payload``."""

import secrets
import struct
from dataclasses import dataclass
from enum import IntEnum

PROTOCOL_VERSION = 1
MESHTASTIC_DATA_PAYLOAD_MAX = 233
MESSAGE_ID_SIZE = 12
ZERO_MESSAGE_ID = bytes(MESSAGE_ID_SIZE)

# One byte packs the four-bit version and four-bit message type. Message and
# correlation IDs are fixed-width so decoding never needs protobuf or JSON.
_HEADER = struct.Struct(f"!B{MESSAGE_ID_SIZE}s{MESSAGE_ID_SIZE}s")
_THREAD_ID = struct.Struct("!I")
_OBJECT_REF = struct.Struct(f"!B{MESSAGE_ID_SIZE}s")
MAX_ENVELOPE_PAYLOAD = MESHTASTIC_DATA_PAYLOAD_MAX - _HEADER.size
MAX_POST_BODY_BYTES = MAX_ENVELOPE_PAYLOAD - _THREAD_ID.size
MAX_SYNC_POST_BODY_BYTES = MAX_ENVELOPE_PAYLOAD - MESSAGE_ID_SIZE
MAX_THREAD_TITLE_BYTES = MAX_ENVELOPE_PAYLOAD
MAX_SYNC_REFS = (MAX_ENVELOPE_PAYLOAD - 1) // _OBJECT_REF.size
MAX_WANT_REFS = MAX_ENVELOPE_PAYLOAD // _OBJECT_REF.size
SYNC_REPLY_REQUESTED = 0x01


class ProtocolError(ValueError):
    """Raised when a SOLoRa frame cannot be safely encoded or decoded."""


class MessageType(IntEnum):
    """SOLoRa v1 application operations."""

    POST = 1
    COMMIT_ACK = 2
    WANT = 3
    SYNC = 4
    THREAD = 5
    SYNC_POST = 6


class ObjectKind(IntEnum):
    """Immutable object categories advertised during repair."""

    THREAD = 1
    POST = 2


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """Compact globally unique reference used by SYNC and WANT."""

    kind: ObjectKind
    object_id: bytes

    def __post_init__(self) -> None:
        _validate_id(self.object_id, "object_id", allow_zero=False)


@dataclass(frozen=True, slots=True)
class PacketEnvelope:
    """A compact SOLoRa message contained in one Meshtastic payload."""

    message_type: MessageType
    message_id: bytes
    payload: bytes = b""
    correlation_id: bytes = ZERO_MESSAGE_ID
    version: int = PROTOCOL_VERSION

    def encode(self) -> bytes:
        _validate_id(self.message_id, "message_id", allow_zero=False)
        _validate_id(self.correlation_id, "correlation_id", allow_zero=True)
        if not 0 < self.version < 16:
            raise ProtocolError("Protocol version must fit in four bits")
        if len(self.payload) > MAX_ENVELOPE_PAYLOAD:
            raise ProtocolError("Envelope exceeds Meshtastic Data.payload limit")

        discriminator = (self.version << 4) | int(self.message_type)
        frame = _HEADER.pack(discriminator, self.message_id, self.correlation_id) + self.payload
        if len(frame) > MESHTASTIC_DATA_PAYLOAD_MAX:
            raise ProtocolError("Frame exceeds Meshtastic Data.payload limit")
        return frame

    @classmethod
    def decode(cls, frame: bytes) -> "PacketEnvelope":
        if len(frame) < _HEADER.size or len(frame) > MESHTASTIC_DATA_PAYLOAD_MAX:
            raise ProtocolError("Invalid SOLoRa frame length")

        discriminator, message_id, correlation_id = _HEADER.unpack_from(frame)
        version = discriminator >> 4
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"Unsupported SOLoRa protocol version: {version}")
        try:
            message_type = MessageType(discriminator & 0x0F)
        except ValueError as error:
            raise ProtocolError("Unknown SOLoRa message type") from error

        _validate_id(message_id, "message_id", allow_zero=False)
        if message_type is MessageType.COMMIT_ACK:
            _validate_id(correlation_id, "correlation_id", allow_zero=False)
        elif correlation_id != ZERO_MESSAGE_ID:
            raise ProtocolError("Only acknowledgements may carry a correlation ID")

        payload = frame[_HEADER.size :]
        if message_type is MessageType.COMMIT_ACK and payload:
            raise ProtocolError("COMMIT_ACK must not contain a payload")
        return cls(message_type, message_id, payload, correlation_id, version)


def new_message_id() -> bytes:
    """Return a compact, non-zero 96-bit application identifier."""
    while True:
        message_id = secrets.token_bytes(MESSAGE_ID_SIZE)
        if message_id != ZERO_MESSAGE_ID:
            return message_id


def encode_post_payload(thread_id: int, body: str) -> bytes:
    """Encode a post body without JSON or redundant length fields."""
    normalized_body = body.strip()
    if not normalized_body:
        raise ProtocolError("Post body must not be empty")
    if not 0 < thread_id <= 0xFFFFFFFF:
        raise ProtocolError("Thread ID must fit in an unsigned 32-bit integer")

    encoded_body = normalized_body.encode("utf-8")
    if len(encoded_body) > MAX_POST_BODY_BYTES:
        raise ProtocolError(
            f"Post requires {len(encoded_body)} bytes; maximum is {MAX_POST_BODY_BYTES}"
        )
    return _THREAD_ID.pack(thread_id) + encoded_body


def decode_post_payload(payload: bytes) -> tuple[int, str]:
    """Decode and validate a v1 POST payload."""
    if len(payload) <= _THREAD_ID.size:
        raise ProtocolError("POST payload is incomplete")
    thread_id = _THREAD_ID.unpack_from(payload)[0]
    try:
        body = payload[_THREAD_ID.size :].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolError("POST body is not valid UTF-8") from error
    normalized_body = body.strip()
    if not normalized_body:
        raise ProtocolError("POST body must not be empty")
    return thread_id, normalized_body


def encode_thread_payload(title: str) -> bytes:
    """Encode a single-frame immutable thread title."""
    return _encode_text(title, MAX_THREAD_TITLE_BYTES, "Thread title")


def decode_thread_payload(payload: bytes) -> str:
    """Decode a single-frame immutable thread title."""
    return _decode_text(payload, "Thread title")


def encode_sync_post_payload(thread_sync_id: bytes, body: str) -> bytes:
    """Encode a post using its thread's global synchronization ID."""
    _validate_id(thread_sync_id, "thread_sync_id", allow_zero=False)
    return thread_sync_id + _encode_text(body, MAX_SYNC_POST_BODY_BYTES, "Post")


def decode_sync_post_payload(payload: bytes) -> tuple[bytes, str]:
    """Decode a post associated with a global thread ID."""
    if len(payload) <= MESSAGE_ID_SIZE:
        raise ProtocolError("SYNC_POST payload is incomplete")
    thread_sync_id = payload[:MESSAGE_ID_SIZE]
    _validate_id(thread_sync_id, "thread_sync_id", allow_zero=False)
    return thread_sync_id, _decode_text(payload[MESSAGE_ID_SIZE:], "Post")


def encode_sync_payload(
    refs: tuple[ObjectRef, ...],
    *,
    reply_requested: bool,
) -> bytes:
    """Encode one inventory page; callers split larger inventories."""
    if len(refs) > MAX_SYNC_REFS:
        raise ProtocolError(f"SYNC carries at most {MAX_SYNC_REFS} object references")
    flags = SYNC_REPLY_REQUESTED if reply_requested else 0
    return bytes([flags]) + _encode_refs(refs)


def decode_sync_payload(payload: bytes) -> tuple[bool, tuple[ObjectRef, ...]]:
    """Decode one inventory page and its response request flag."""
    if not payload or payload[0] & ~SYNC_REPLY_REQUESTED:
        raise ProtocolError("Invalid SYNC flags")
    refs = _decode_refs(payload[1:])
    if len(refs) > MAX_SYNC_REFS:
        raise ProtocolError("SYNC contains too many object references")
    return bool(payload[0] & SYNC_REPLY_REQUESTED), refs


def encode_want_payload(refs: tuple[ObjectRef, ...]) -> bytes:
    """Encode requested object references."""
    if not refs or len(refs) > MAX_WANT_REFS:
        raise ProtocolError(f"WANT carries between 1 and {MAX_WANT_REFS} references")
    return _encode_refs(refs)


def decode_want_payload(payload: bytes) -> tuple[ObjectRef, ...]:
    """Decode requested object references."""
    refs = _decode_refs(payload)
    if not refs or len(refs) > MAX_WANT_REFS:
        raise ProtocolError("Invalid WANT reference count")
    return refs


def message_id_hex(message_id: bytes) -> str:
    """Return the stable API/log representation of an application ID."""
    _validate_id(message_id, "message_id", allow_zero=False)
    return message_id.hex()


def _validate_id(value: bytes, name: str, *, allow_zero: bool) -> None:
    if len(value) != MESSAGE_ID_SIZE:
        raise ProtocolError(f"{name} must be {MESSAGE_ID_SIZE} bytes")
    if not allow_zero and value == ZERO_MESSAGE_ID:
        raise ProtocolError(f"{name} must not be zero")


def _encode_refs(refs: tuple[ObjectRef, ...]) -> bytes:
    return b"".join(_OBJECT_REF.pack(int(ref.kind), ref.object_id) for ref in refs)


def _decode_refs(payload: bytes) -> tuple[ObjectRef, ...]:
    if len(payload) % _OBJECT_REF.size:
        raise ProtocolError("Object reference list is truncated")
    refs: list[ObjectRef] = []
    for offset in range(0, len(payload), _OBJECT_REF.size):
        kind_value, object_id = _OBJECT_REF.unpack_from(payload, offset)
        try:
            kind = ObjectKind(kind_value)
        except ValueError as error:
            raise ProtocolError("Unknown object kind") from error
        refs.append(ObjectRef(kind, object_id))
    if len(set(refs)) != len(refs):
        raise ProtocolError("Object reference list contains duplicates")
    return tuple(refs)


def _encode_text(value: str, maximum: int, label: str) -> bytes:
    normalized = value.strip()
    if not normalized:
        raise ProtocolError(f"{label} must not be empty")
    encoded = normalized.encode("utf-8")
    if len(encoded) > maximum:
        raise ProtocolError(f"{label} requires {len(encoded)} bytes; maximum is {maximum}")
    return encoded


def _decode_text(payload: bytes, label: str) -> str:
    if not payload:
        raise ProtocolError(f"{label} must not be empty")
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolError(f"{label} is not valid UTF-8") from error
    normalized = decoded.strip()
    if not normalized:
        raise ProtocolError(f"{label} must not be empty")
    return normalized
