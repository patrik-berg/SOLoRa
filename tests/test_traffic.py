"""Passive capture, privacy, presentation, SSE and runtime wiring contracts."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_app import _database_url, _migrate
from test_meshtastic_transport import FakeInterface, FakePublisher, _channel

from solora.adapters.persistence.sync_repository import SqlAlchemySyncRepository
from solora.adapters.transport import meshtastic
from solora.adapters.transport.in_memory import InMemoryNetwork
from solora.adapters.transport.meshtastic import PRIVATE_APP_TOPIC, MeshtasticTransport
from solora.application.sync import SyncNode
from solora.application.traffic import TrafficBuffer, TrafficObservation, TrafficSink, observe
from solora.application.transport_ports import InboundFrame, TrafficPriority, TransportError
from solora.domain.meshtastic_settings import MeshtasticChannelSelection
from solora.domain.protocol import (
    MessageType,
    ObjectKind,
    ObjectRef,
    PacketEnvelope,
    encode_post_payload,
    encode_sync_payload,
    encode_sync_post_payload,
    encode_thread_payload,
    encode_want_payload,
)
from solora.web.application import create_app
from solora.web.traffic import events

ID = b"a" * 12
REF = ObjectRef(ObjectKind.THREAD, b"t" * 12)


def frame(kind: MessageType = MessageType.THREAD, payload: bytes | None = None) -> bytes:
    return PacketEnvelope(
        kind,
        ID,
        payload if payload is not None else b"Nyheter",
        b"b" * 12 if kind is MessageType.COMMIT_ACK else bytes(12),
    ).encode()


def capture(buffer: TrafficBuffer, raw: bytes | None = None) -> None:
    buffer.capture(
        TrafficObservation("RX", 10, 11, frame() if raw is None else raw, "solora-link", 3, 256)
    )


@pytest.mark.parametrize(
    "kind,payload,field",
    [
        (MessageType.POST, encode_post_payload(1, "hej"), "thread_local_id"),
        (MessageType.THREAD, encode_thread_payload("nyheter"), "title"),
        (MessageType.SYNC_POST, encode_sync_post_payload(ID, "hej"), "thread_id"),
        (MessageType.WANT, encode_want_payload((REF,)), "objects"),
        (MessageType.SYNC, encode_sync_payload((REF,), reply_requested=True), "reply_requested"),
        (MessageType.COMMIT_ACK, b"", "application"),
    ],
)
def test_decoders_reuse_protocol_and_preserve_exact_bytes(
    kind: MessageType, payload: bytes, field: str
) -> None:
    buffer = TrafficBuffer()
    raw = frame(kind, payload)
    capture(buffer, raw)
    event = buffer.snapshot()["events"][0]
    assert event["raw_hex"] == raw.hex()
    assert event["payload_size"] == len(raw)
    assert event["message_type"] == kind.name
    assert event["message_id"] == ID.hex()
    assert field in event["parsed_fields"]
    assert event["decode_state"] == "decoded"
    if kind is MessageType.COMMIT_ACK:
        assert "not a Meshtastic routing ACK" in event["parsed_fields"][field]


@pytest.mark.parametrize(
    "raw", [b"\x15", frame(MessageType.SYNC_POST, b"short"), frame(MessageType.THREAD, b"\xff")]
)
def test_malformed_known_frames_keep_hex_without_crashing(raw: bytes) -> None:
    buffer = TrafficBuffer()
    capture(buffer, raw)
    event = buffer.snapshot()["events"][0]
    assert event["decode_state"] == "error"
    assert event["raw_hex"] == raw.hex()


@pytest.mark.parametrize(
    "raw",
    [
        b"\x1cpassword-secret",
        b"\x1dtoken-secret",
        b"\x25future-secret",
        b"\x1funknown-secret",
        b"",
        b"\x15" + b"secret" * 100,
    ],
)
def test_sensitive_unknown_or_oversized_bytes_not_even_retained(raw: bytes) -> None:
    buffer = TrafficBuffer()
    capture(buffer, raw)
    assert buffer._events[0].observation.payload == b""
    event = buffer.snapshot()["events"][0]
    assert event["raw_hex"] is None
    assert event["message_id"] is None
    assert event["redacted"] is True
    assert raw.hex() not in json.dumps(event) if raw else True


def test_ring_eviction_clear_cursor_and_contention_are_bounded() -> None:
    buffer = TrafficBuffer(2)
    for _ in range(3):
        capture(buffer)
    assert [e["sequence"] for e in buffer.snapshot()["events"]] == [2, 3]
    assert len(buffer.snapshot(2)["events"]) == 1
    with buffer._lock:
        capture(buffer)
    assert buffer.snapshot()["revision"] == 3
    buffer.clear()
    assert buffer.snapshot()["events"] == []
    assert buffer.snapshot()["oldest"] == 5
    capture(buffer)
    assert buffer.snapshot()["events"][0]["sequence"] == 5
    with pytest.raises(ValueError):
        TrafficBuffer(0)


def radio(
    buffer: TrafficSink, index: int = 3
) -> tuple[MeshtasticTransport, FakeInterface, FakePublisher]:
    interface = FakeInterface(channels=[_channel(index, "solora-link")])
    publisher = FakePublisher()
    transport = MeshtasticTransport(
        interface,
        publisher,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        channel_index=index,
        channel_name="solora-link",
        traffic_sink=buffer,
    )
    return transport, interface, publisher


@pytest.mark.parametrize("index", [1, 5])
def test_tx_rx_channel_bytes_filtering_and_safe_metadata(index: int) -> None:
    buffer = TrafficBuffer()
    transport, interface, pub = radio(buffer, index)
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)
    raw = frame()
    transport.send(11, raw, priority=TrafficPriority.USER)
    packet = {
        "from": 11,
        "to": 10,
        "channel": index,
        "decoded": {"portnum": "PRIVATE_APP", "payload": raw},
        "psk": "secret",
    }
    pub.publish(PRIVATE_APP_TOPIC, packet, interface)
    for wrong in [
        {**packet, "channel": (index + 1) % 8},
        {**packet, "decoded": {"portnum": "ROUTING_APP", "payload": raw}},
        {**packet, "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": raw}},
    ]:
        pub.publish(PRIVATE_APP_TOPIC, wrong, interface)
    pub.publish(PRIVATE_APP_TOPIC, packet, FakeInterface())
    result = buffer.snapshot()["events"]
    assert len(result) == 2 and len(received) == 1
    assert [e["direction"] for e in result] == ["TX", "RX"]
    assert result[0]["source"] == result[1]["destination"] == 10
    assert all(e["channel_index"] == index for e in result)
    assert all(e["channel_name"] == "solora-link" for e in result)
    assert result[0]["raw_hex"] == interface.sent[0][0].hex() == result[1]["raw_hex"]
    assert result[0]["packet_id"] == 1234
    assert "secret" not in json.dumps(result)
    assert [entry["name"] for entry in buffer.snapshot()["registry"]] == [
        k.name for k in MessageType
    ]


def test_logging_failures_do_not_stop_radio_and_send_errors_are_explicit() -> None:
    class Broken:
        def capture(self, observation: TrafficObservation) -> None:
            raise RuntimeError("presentation failed")

    transport, interface, pub = radio(Broken())
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)
    transport.send(11, frame(), priority=TrafficPriority.USER)
    pub.publish(
        PRIVATE_APP_TOPIC,
        {"from": 11, "to": 10, "channel": 3, "decoded": {"portnum": 256, "payload": frame()}},
        interface,
    )
    assert len(interface.sent) == len(received) == 1
    buffer = TrafficBuffer()
    transport, interface, _ = radio(buffer)
    interface.error = RuntimeError("secret SDK error")
    with pytest.raises(TransportError):
        transport.send(11, frame(), priority=TrafficPriority.USER)
    assert buffer.snapshot()["events"][0]["status"] == "Transport error"
    assert "secret" not in json.dumps(buffer.snapshot())
    observe(None, TrafficObservation("TX", 1, 2, b""))


def test_virtual_two_node_loss_replay_capture_does_not_inject() -> None:
    network = InMemoryNetwork()
    a_log = TrafficBuffer()
    b_log = TrafficBuffer()
    a = network.connect(1, traffic_sink=a_log)
    b = network.connect(2, traffic_sink=b_log)
    received: list[InboundFrame] = []
    b.set_receiver(received.append)
    network.drop_next()
    a.send(2, frame(), priority=TrafficPriority.USER)
    assert b_log.snapshot()["events"] == []
    a.send(2, frame(), priority=TrafficPriority.USER)
    network.replay(network.transmissions[-1])
    assert len(a_log.snapshot()["events"]) == len(b_log.snapshot()["events"]) == 2
    assert len(network.transmissions) == 2
    assert b_log.snapshot()["events"][0]["portnum"] is None


def test_http_reads_clear_export_and_sse_are_passive(tmp_path: Path) -> None:
    url = _database_url(tmp_path)
    _migrate(url)
    app = create_app(database_url=url)
    with TestClient(app) as client:
        thread = client.post("/api/threads", json={"title": "Keep me"}).json()
        capture(app.state.traffic)
        for _ in range(3):
            assert len(client.get("/api/traffic").json()["events"]) == 1
            client.get("/api/status")
        exported = client.get("/api/traffic/export")
        assert exported.json()["format"] == "SOLoRa Traffic Log"
        assert exported.json()["protocol_version"] == 1
        assert "attachment" in exported.headers["content-disposition"]
        assert client.delete("/api/traffic").json()["events"] == []
        assert client.get(f"/api/threads/{thread['id']}").json()["title"] == "Keep me"
        assert app.state.meshtastic_settings._gateway.connected is False

    async def check_stream() -> None:
        request = cast(Request, SimpleNamespace(is_disconnected=AsyncMock(return_value=False)))
        buffer = TrafficBuffer()
        capture(buffer)
        stream = events(buffer, request)
        assert '"sequence": 1' in await anext(stream)
        buffer.clear()
        assert '"events": []' in await anext(stream)
        await stream.aclose()
        capture(buffer)
        reconnect = events(buffer, request)
        assert '"sequence": 3' in await anext(reconnect)
        await reconnect.aclose()

    asyncio.run(check_stream())


def test_web_connection_observes_confirmed_channel_without_extra_tx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface = FakeInterface(channels=[_channel(2, "solora-link"), _channel(5, "backup")])
    publisher = FakePublisher()
    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, lambda *args, **kwargs: interface),
        tcp_factory=cast(meshtastic._TCPFactory, lambda *args, **kwargs: interface),
        list_ports=lambda: (),
        publisher=publisher,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)
    url = _database_url(tmp_path)
    _migrate(url)
    app = create_app(database_url=url)
    with TestClient(app) as client:
        client.post(
            "/api/settings/meshtastic/test", json={"connection_type": "usb", "endpoint": "COM3"}
        )
        assert PRIVATE_APP_TOPIC not in publisher.listeners
        response = client.put(
            "/api/settings/meshtastic/channel",
            json={"channel_index": 2, "channel_name": "solora-link"},
        )
        assert response.status_code == 200
        packet = {
            "from": 11,
            "to": 10,
            "channel": 2,
            "decoded": {"portnum": 256, "payload": frame()},
        }
        publisher.publish(PRIVATE_APP_TOPIC, packet, interface)
        for _ in range(3):
            assert client.get("/api/traffic").json()["events"][0]["channel_index"] == 2
            client.get("/api/status")
            client.get("/api/traffic/export")
        client.put(
            "/api/settings/meshtastic/channel", json={"channel_index": 5, "channel_name": "backup"}
        )
        publisher.publish(PRIVATE_APP_TOPIC, packet, interface)  # old channel ignored
        publisher.publish(PRIVATE_APP_TOPIC, {**packet, "channel": 5}, interface)
        result = client.get("/api/traffic").json()["events"]
        assert [event["channel_name"] for event in result] == ["solora-link", "backup"]
        assert not interface.closed  # replacing observer must not close shared connection
        gateway = app.state.meshtastic_settings._gateway
        gateway.observe_channel(MeshtasticChannelSelection(999, 5, "backup"))
        assert gateway._traffic_transport is None
        client.post("/api/settings/meshtastic/refresh")
        assert gateway._traffic_transport is not None
        gateway._on_connection_lost(interface=interface)
        assert gateway._traffic_transport is None
        assert interface.sent == []
    assert interface.closed


def test_unexpected_sink_failure_and_invalid_send_result_leave_protocol_unchanged() -> None:
    buffer = TrafficBuffer()
    transport, interface, _ = radio(buffer)
    interface.result = SimpleNamespace(id=0)
    with pytest.raises(TransportError):
        transport.send(11, frame(), priority=TrafficPriority.USER)
    assert buffer.snapshot()["events"][0]["status"] == "Transport error"
    interface.queueStatus = SimpleNamespace(free=0)
    with pytest.raises(TransportError):
        transport.send(11, frame(), priority=TrafficPriority.USER)
    assert len(buffer.snapshot()["events"]) == 1  # never handed to SDK


def test_clear_preserves_populated_outbox_dedupe_and_forum(tmp_path: Path) -> None:
    url = _database_url(tmp_path)
    _migrate(url)
    app = create_app(database_url=url)
    with TestClient(app) as client, app.state.database.sessions() as session:
        thread = client.post("/api/threads", json={"title": "Durable"}).json()
        network = InMemoryNetwork()
        node = SyncNode(
            SqlAlchemySyncRepository(session), network.connect(10, traffic_sink=app.state.traffic)
        )
        node.publish_post(thread["id"], "Waiting for peer", destination=11)
        node.receive(InboundFrame(11, 10, frame()))
        tables = ("outbox", "received_messages", "threads", "posts", "repair_requests")
        before = {table: session.execute(text(f"SELECT * FROM {table}")).all() for table in tables}
        assert before["outbox"] and before["received_messages"] and before["posts"]
        attempts = len(network.transmissions)
        client.delete("/api/traffic")
        after = {table: session.execute(text(f"SELECT * FROM {table}")).all() for table in tables}
        assert after == before
        assert len(network.transmissions) == attempts
