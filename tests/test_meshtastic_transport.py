"""Hardware-free contract tests for the official Meshtastic adapter."""

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest

from solora.adapters.transport import meshtastic
from solora.adapters.transport.meshtastic import (
    BROADCAST_NODE_ID,
    PRIVATE_APP_TOPIC,
    MeshtasticTransport,
    MeshtasticUnavailableError,
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


class FakeInterface:
    def __init__(self, node_id: int = 0xA) -> None:
        self.myInfo = SimpleNamespace(my_node_num=node_id)
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
            "decoded": {"portnum": "PRIVATE_APP", "payload": bytearray(b"frame")},
        },
        interface,
    )
    publisher.publish(
        PRIVATE_APP_TOPIC,
        {
            "from": 0xB,
            "to": 0xA,
            "decoded": {
                "portnum": "ROUTING_APP",
                "payload": b"transport acknowledgement",
            },
        },
        interface,
    )

    assert received == [InboundFrame(source=0xB, destination=0xA, payload=b"frame")]


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
    parameters = {
        "private_app": 256,
        "payload_limit": 233,
        "background_priority": 10,
        "reliable_priority": 70,
        **kwargs,
    }

    with pytest.raises(ValueError, match=message):
        MeshtasticTransport(FakeInterface(), FakePublisher(), **parameters)
