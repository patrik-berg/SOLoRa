"""Hardware-free contract tests for the official Meshtastic adapter."""

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from solora.adapters.transport import meshtastic
from solora.adapters.transport.meshtastic import (
    BROADCAST_NODE_ID,
    PRIVATE_APP_TOPIC,
    MeshtasticTransport,
    MeshtasticUnavailableError,
    SerialMeshtasticChannelDiscovery,
)
from solora.application.transport_ports import InboundFrame, TrafficPriority, TransportError
from solora.domain.protocol import MESHTASTIC_DATA_PAYLOAD_MAX


class FakePublisher:
    def __init__(self) -> None:
        self.listeners: dict[str, Callable[..., None]] = {}
        self.unsubscribed: list[str] = []

    def subscribe(self, listener: Callable[..., None], topic_name: str) -> None:
        self.listeners[topic_name] = listener

    def unsubscribe(self, listener: Callable[..., None], topic_name: str) -> None:
        assert self.listeners[topic_name] == listener
        self.unsubscribed.append(topic_name)

    def publish(self, topic: str, packet: object, interface: object) -> None:
        self.listeners[topic](packet=packet, interface=interface)


@dataclass
class FakePacket:
    id: int = 1234


def _channel(index: int, name: str, role: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        index=index, role=role, settings=SimpleNamespace(name=name, psk=b"secret")
    )


class FakeInterface:
    def __init__(
        self,
        node_id: int = 0xA,
        channels: list[SimpleNamespace] | None = None,
    ) -> None:
        self.myInfo = SimpleNamespace(my_node_num=node_id)
        self.localNode = SimpleNamespace(channels=channels or [_channel(0, "Primary", 1)])
        self.queueStatus: object | None = SimpleNamespace(free=2)
        self.sent: list[tuple[bytes, int, dict[str, object]]] = []
        self.result: object = FakePacket()
        self.error: Exception | None = None
        self.closed = False

    def sendData(  # noqa: N802 - mirrors the official Meshtastic API
        self,
        data: bytes,
        destination_id: int,
        **kwargs: object,
    ) -> object:
        if self.error is not None:
            raise self.error
        self.sent.append((data, destination_id, kwargs))
        return self.result

    def close(self) -> None:
        self.closed = True


def _transport(
    interface: FakeInterface | None = None,
    publisher: FakePublisher | None = None,
) -> tuple[MeshtasticTransport, FakeInterface, FakePublisher]:
    selected_interface = interface or FakeInterface()
    selected_publisher = publisher or FakePublisher()
    transport = MeshtasticTransport(
        selected_interface,
        selected_publisher,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        channel_index=2,
        hop_limit=3,
    )
    return transport, selected_interface, selected_publisher


def test_send_maps_unicast_payload_port_priority_and_result() -> None:
    transport, interface, _publisher = _transport()

    transport.send(0xB, b"solora", priority=TrafficPriority.USER)

    assert interface.sent == [
        (
            b"solora",
            0xB,
            {
                "portNum": 256,
                "wantAck": True,
                "wantResponse": False,
                "channelIndex": 2,
                "hopLimit": 3,
                "priority": 70,
            },
        )
    ]
    assert transport.last_packet_id == 1234


def test_broadcast_uses_background_queue_without_routing_ack_request() -> None:
    transport, interface, _publisher = _transport()

    transport.send(BROADCAST_NODE_ID, b"repair", priority=TrafficPriority.BACKGROUND)

    assert interface.sent[0][2]["priority"] == 10
    assert interface.sent[0][2]["wantAck"] is False


def test_receive_maps_only_private_app_data_and_never_routing_ack() -> None:
    transport, interface, publisher = _transport()
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)

    publisher.publish(
        PRIVATE_APP_TOPIC,
        {
            "from": 0xB,
            "to": 0xA,
            "channel": 2,
            "decoded": {"portnum": "PRIVATE_APP", "payload": bytearray(b"frame")},
        },
        interface,
    )
    publisher.publish(
        PRIVATE_APP_TOPIC,
        {
            "from": 0xB,
            "to": 0xA,
            "channel": 2,
            "decoded": {
                "portnum": "ROUTING_APP",
                "payload": b"transport acknowledgement",
            },
        },
        interface,
    )

    assert received == [InboundFrame(source=0xB, destination=0xA, payload=b"frame")]


def test_receive_ignores_private_app_on_another_channel() -> None:
    transport, interface, publisher = _transport()
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)

    publisher.publish(
        PRIVATE_APP_TOPIC,
        {
            "from": 0xB,
            "to": 0xA,
            "channel": 1,
            "decoded": {"portnum": 256, "payload": b"not-solora-channel"},
        },
        interface,
    )

    assert received == []


@pytest.mark.parametrize(
    "packet",
    [
        None,
        {},
        {"decoded": {}},
        {"from": True, "to": 1, "decoded": {"portnum": 256, "payload": b"x"}},
        {"from": 0, "to": 1, "decoded": {"portnum": 256, "payload": b"x"}},
        {"from": 1, "to": 0, "decoded": {"portnum": 256, "payload": b"x"}},
        {"from": 1, "to": 2, "decoded": {"portnum": 256, "payload": "text"}},
        {
            "from": 1,
            "to": 2,
            "decoded": {
                "portnum": 256,
                "payload": b"x" * (MESHTASTIC_DATA_PAYLOAD_MAX + 1),
            },
        },
    ],
)
def test_receive_ignores_malformed_packets(packet: object) -> None:
    transport, interface, publisher = _transport()
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)

    publisher.publish(PRIVATE_APP_TOPIC, packet, interface)

    assert received == []


def test_receive_ignores_other_interfaces_and_closed_transport() -> None:
    transport, interface, publisher = _transport()
    received: list[InboundFrame] = []
    transport.set_receiver(received.append)
    packet = {
        "from": 2,
        "to": 1,
        "decoded": {"portnum": 256, "payload": b"x"},
    }

    publisher.publish(PRIVATE_APP_TOPIC, packet, object())
    transport.close()
    publisher.publish(PRIVATE_APP_TOPIC, packet, interface)

    assert received == []
    assert publisher.unsubscribed == [PRIVATE_APP_TOPIC]
    assert interface.closed


def test_send_maps_queue_sdk_and_invalid_result_errors() -> None:
    transport, interface, _publisher = _transport()
    interface.queueStatus = SimpleNamespace(free=0)
    with pytest.raises(TransportError, match="queue is full"):
        transport.send(2, b"x", priority=TrafficPriority.USER)

    interface.queueStatus = None
    interface.error = RuntimeError("serial disconnected")
    with pytest.raises(TransportError, match="serial disconnected"):
        transport.send(2, b"x", priority=TrafficPriority.USER)

    interface.error = None
    interface.result = SimpleNamespace(id=0)
    with pytest.raises(TransportError, match="valid packet ID"):
        transport.send(2, b"x", priority=TrafficPriority.USER)


def test_send_rejects_bad_destination_oversize_and_closed_state() -> None:
    transport, _interface, _publisher = _transport()
    with pytest.raises(TransportError, match="Destination"):
        transport.send(0, b"x", priority=TrafficPriority.USER)
    with pytest.raises(TransportError, match="233"):
        transport.send(2, b"x" * 234, priority=TrafficPriority.USER)

    transport.close()
    transport.close()
    with pytest.raises(TransportError, match="closed"):
        transport.send(2, b"x", priority=TrafficPriority.USER)


def test_open_serial_uses_injected_official_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    interface = FakeInterface(0x1234)
    publisher = FakePublisher()
    opened_devices: list[str | None] = []

    def open_device(device: str | None = None) -> FakeInterface:
        opened_devices.append(device)
        return interface

    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, open_device),
        publisher=publisher,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)

    transport = MeshtasticTransport.open_serial("/dev/tty.fake")

    assert transport.node_id == 0x1234
    assert opened_devices == ["/dev/tty.fake"]


def test_open_serial_closes_interface_when_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface = FakeInterface(node_id=0)
    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, lambda _device=None: interface),
        publisher=FakePublisher(),
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)

    with pytest.raises(TransportError, match="local node ID"):
        MeshtasticTransport.open_serial("/dev/tty.fake")

    assert interface.closed


def test_open_serial_maps_sdk_open_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(_device: str | None = None) -> FakeInterface:
        raise OSError("port busy")

    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, fail_open),
        publisher=FakePublisher(),
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)

    with pytest.raises(TransportError, match="port busy"):
        MeshtasticTransport.open_serial("/dev/tty.busy")


def test_optional_sdk_has_actionable_install_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_module(_name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(meshtastic, "import_module", missing_module)

    with pytest.raises(MeshtasticUnavailableError, match="make setup-radio"):
        meshtastic._load_runtime()


def test_discovery_returns_enabled_public_metadata_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface = FakeInterface(
        0x1234,
        [_channel(0, "", 1), _channel(3, "solora-link"), _channel(4, "hidden", 0)],
    )
    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, lambda _device=None: interface),
        publisher=FakePublisher(),
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)

    result = SerialMeshtasticChannelDiscovery("/dev/test").discover()

    assert result.node_id == 0x1234
    assert [(item.index, item.name, item.role) for item in result.channels] == [
        (0, "", "primary"),
        (3, "solora-link", "secondary"),
    ]
    assert "secret" not in repr(result)
    assert interface.closed


def test_open_serial_requires_exact_enabled_channel_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interface = FakeInterface(channels=[_channel(3, "solora-link")])
    runtime = meshtastic._MeshtasticRuntime(
        serial_factory=cast(meshtastic._SerialFactory, lambda _device=None: interface),
        publisher=FakePublisher(),
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        disabled_channel_role=0,
    )
    monkeypatch.setattr(meshtastic, "_load_runtime", lambda: runtime)

    with pytest.raises(TransportError, match="no longer match"):
        MeshtasticTransport.open_serial(channel_index=3, channel_name="renamed")

    assert interface.closed


def test_two_nodes_can_use_same_channel_name_at_different_local_indices() -> None:
    publisher_a = FakePublisher()
    publisher_b = FakePublisher()
    interface_a = FakeInterface(0xA, [_channel(1, "solora-link")])
    interface_b = FakeInterface(0xB, [_channel(4, "solora-link")])
    transport_a = MeshtasticTransport(
        interface_a,
        publisher_a,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        channel_index=1,
        channel_name="solora-link",
    )
    transport_b = MeshtasticTransport(
        interface_b,
        publisher_b,
        private_app=256,
        payload_limit=233,
        background_priority=10,
        reliable_priority=70,
        channel_index=4,
        channel_name="solora-link",
    )

    transport_a.send(0xB, b"a", priority=TrafficPriority.USER)
    transport_b.send(0xA, b"b", priority=TrafficPriority.USER)

    assert interface_a.sent[0][2]["channelIndex"] == 1
    assert interface_b.sent[0][2]["channelIndex"] == 4


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"payload_limit": 0}, "payload limit"),
        ({"channel_index": 8}, "channel index"),
        ({"hop_limit": 8}, "hop limit"),
    ],
)
def test_constructor_validates_official_limits(
    kwargs: dict[str, int],
    message: str,
) -> None:
    parameters: dict[str, Any] = {
        "private_app": 256,
        "payload_limit": 233,
        "background_priority": 10,
        "reliable_priority": 70,
        **kwargs,
    }

    with pytest.raises(ValueError, match=message):
        MeshtasticTransport(FakeInterface(), FakePublisher(), **parameters)
