"""Contract tests for the compact SOLoRa v1 packet envelope."""

from pathlib import Path

import pytest

from solora.domain.protocol import (
    MAX_POST_BODY_BYTES,
    MESHTASTIC_DATA_PAYLOAD_MAX,
    ZERO_MESSAGE_ID,
    MessageType,
    PacketEnvelope,
    ProtocolError,
    decode_post_payload,
    encode_post_payload,
)

MESSAGE_ID = bytes.fromhex("0102030405060708090a0b0c")
ACK_ID = bytes.fromhex("1112131415161718191a1b1c")
FIXTURES = Path(__file__).resolve().parents[1] / "protocol" / "fixtures"


def _fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="utf-8"))


def test_canonical_frames_match_versioned_fixtures() -> None:
    post = PacketEnvelope(
        MessageType.POST,
        MESSAGE_ID,
        encode_post_payload(42, "hej"),
    ).encode()
    acknowledgement = PacketEnvelope(
        MessageType.COMMIT_ACK,
        ACK_ID,
        correlation_id=MESSAGE_ID,
    ).encode()

    assert post == _fixture("v1-post.hex")
    assert acknowledgement == _fixture("v1-commit-ack.hex")


def test_post_envelope_round_trips_at_meshtastic_limit() -> None:
    payload = encode_post_payload(42, "x" * MAX_POST_BODY_BYTES)
    frame = PacketEnvelope(MessageType.POST, MESSAGE_ID, payload).encode()

    decoded = PacketEnvelope.decode(frame)

    assert len(frame) == MESHTASTIC_DATA_PAYLOAD_MAX
    assert decoded.message_type is MessageType.POST
    assert decoded.message_id == MESSAGE_ID
    assert decode_post_payload(decoded.payload) == (42, "x" * MAX_POST_BODY_BYTES)


def test_commit_ack_correlates_without_application_payload() -> None:
    frame = PacketEnvelope(
        MessageType.COMMIT_ACK,
        ACK_ID,
        correlation_id=MESSAGE_ID,
    ).encode()

    decoded = PacketEnvelope.decode(frame)

    assert decoded.correlation_id == MESSAGE_ID
    assert decoded.payload == b""


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        bytes([0x21]) + MESSAGE_ID + ZERO_MESSAGE_ID,
        bytes([0x1F]) + MESSAGE_ID + ZERO_MESSAGE_ID,
        bytes([0x11]) + ZERO_MESSAGE_ID + ZERO_MESSAGE_ID,
        bytes([0x12]) + ACK_ID + ZERO_MESSAGE_ID,
        bytes([0x12]) + ACK_ID + MESSAGE_ID + b"unexpected",
    ],
)
def test_decoder_rejects_invalid_frames(frame: bytes) -> None:
    with pytest.raises(ProtocolError):
        PacketEnvelope.decode(frame)


def test_post_payload_enforces_utf8_byte_budget() -> None:
    with pytest.raises(ProtocolError, match="maximum"):
        encode_post_payload(1, "å" * MAX_POST_BODY_BYTES)

    with pytest.raises(ProtocolError, match="UTF-8"):
        decode_post_payload(b"\x00\x00\x00\x01\xff")
