"""Contract tests for the compact SOLoRa v1 packet envelope."""

from pathlib import Path

import pytest

from solora.domain.protocol import (
    MAX_POST_BODY_BYTES,
    MAX_SYNC_POST_BODY_BYTES,
    MAX_SYNC_REFS,
    MAX_WANT_REFS,
    MESHTASTIC_DATA_PAYLOAD_MAX,
    ZERO_MESSAGE_ID,
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
    encode_post_payload,
    encode_sync_payload,
    encode_sync_post_payload,
    encode_thread_payload,
    encode_want_payload,
)

MESSAGE_ID = bytes.fromhex("0102030405060708090a0b0c")
ACK_ID = bytes.fromhex("1112131415161718191a1b1c")
THREAD_ID = bytes.fromhex("2122232425262728292a2b2c")
POST_ID = bytes.fromhex("3132333435363738393a3b3c")
SYNC_ID = bytes.fromhex("4142434445464748494a4b4c")
WANT_ID = bytes.fromhex("5152535455565758595a5b5c")
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
    refs = (
        ObjectRef(ObjectKind.THREAD, THREAD_ID),
        ObjectRef(ObjectKind.POST, POST_ID),
    )
    thread = PacketEnvelope(
        MessageType.THREAD,
        THREAD_ID,
        encode_thread_payload("Tråd"),
    ).encode()
    sync_post = PacketEnvelope(
        MessageType.SYNC_POST,
        POST_ID,
        encode_sync_post_payload(THREAD_ID, "Hej"),
    ).encode()
    sync = PacketEnvelope(
        MessageType.SYNC,
        SYNC_ID,
        encode_sync_payload(refs, reply_requested=True),
    ).encode()
    want = PacketEnvelope(
        MessageType.WANT,
        WANT_ID,
        encode_want_payload(refs),
    ).encode()

    assert post == _fixture("v1-post.hex")
    assert acknowledgement == _fixture("v1-commit-ack.hex")
    assert thread == _fixture("v1-thread.hex")
    assert sync_post == _fixture("v1-sync-post.hex")
    assert sync == _fixture("v1-sync.hex")
    assert want == _fixture("v1-want.hex")


def test_sync_object_payloads_round_trip() -> None:
    assert decode_thread_payload(encode_thread_payload("  Gemensam tråd  ")) == "Gemensam tråd"
    assert decode_sync_post_payload(encode_sync_post_payload(THREAD_ID, "  Text  ")) == (
        THREAD_ID,
        "Text",
    )


def test_sync_and_want_reference_pages_round_trip_at_limits() -> None:
    sync_refs = tuple(
        ObjectRef(ObjectKind.POST, index.to_bytes(12)) for index in range(1, MAX_SYNC_REFS + 1)
    )
    want_refs = tuple(
        ObjectRef(ObjectKind.POST, index.to_bytes(12)) for index in range(1, MAX_WANT_REFS + 1)
    )

    sync_payload = encode_sync_payload(sync_refs, reply_requested=True)
    want_payload = encode_want_payload(want_refs)

    assert decode_sync_payload(sync_payload) == (True, sync_refs)
    assert decode_want_payload(want_payload) == want_refs
    assert len(PacketEnvelope(MessageType.SYNC, SYNC_ID, sync_payload).encode()) <= 233
    assert len(PacketEnvelope(MessageType.WANT, WANT_ID, want_payload).encode()) == 233


def test_sync_payload_validation_rejects_malformed_data() -> None:
    duplicate = ObjectRef(ObjectKind.THREAD, THREAD_ID)
    with pytest.raises(ProtocolError, match="duplicates"):
        decode_want_payload(encode_want_payload((duplicate, duplicate)))
    with pytest.raises(ProtocolError, match="truncated"):
        decode_sync_payload(b"\x00\x01")
    with pytest.raises(ProtocolError, match="flags"):
        decode_sync_payload(b"\x80")
    with pytest.raises(ProtocolError, match="between"):
        encode_want_payload(())
    with pytest.raises(ProtocolError, match="maximum"):
        encode_sync_post_payload(THREAD_ID, "x" * (MAX_SYNC_POST_BODY_BYTES + 1))


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
