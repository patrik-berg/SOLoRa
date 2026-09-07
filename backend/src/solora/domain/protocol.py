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
MAX_ENVELOPE_PAYLOAD = MESHTASTIC_DATA_PAYLOAD_MAX - _HEADER.size
MAX_POST_BODY_BYTES = MAX_ENVELOPE_PAYLOAD - _THREAD_ID.size


class ProtocolError(ValueError):
    """Raised when a SOLoRa frame cannot be safely encoded or decoded."""


class MessageType(IntEnum):
    """SOLoRa v1 application operations."""

    POST = 1
    COMMIT_ACK = 2
    WANT = 3
    SYNC = 4


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


def message_id_hex(message_id: bytes) -> str:
    """Return the stable API/log representation of an application ID."""
    _validate_id(message_id, "message_id", allow_zero=False)
    return message_id.hex()


def _validate_id(value: bytes, name: str, *, allow_zero: bool) -> None:
    if len(value) != MESSAGE_ID_SIZE:
        raise ProtocolError(f"{name} must be {MESSAGE_ID_SIZE} bytes")
    if not allow_zero and value == ZERO_MESSAGE_ID:
        raise ProtocolError(f"{name} must not be zero")
