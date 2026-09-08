"""Thin adapter from SOLoRa's transport port to Meshtastic Python."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, TypeGuard, cast

from solora.application.transport_ports import (
    FrameReceiver,
    InboundFrame,
    TrafficPriority,
    TransportError,
)
from solora.domain.meshtastic_settings import (
    MeshtasticChannel,
    MeshtasticConnectionConfig,
    MeshtasticConnectionType,
    MeshtasticDevice,
    MeshtasticNodeChannels,
)
from solora.domain.protocol import MESHTASTIC_DATA_PAYLOAD_MAX

PRIVATE_APP_TOPIC = "meshtastic.receive.data.PRIVATE_APP"
CONNECTION_LOST_TOPIC = "meshtastic.connection.lost"
BROADCAST_NODE_ID = 0xFFFFFFFF
CONNECTION_TIMEOUT_SECONDS = 15


class MeshtasticUnavailableError(TransportError):
    """Raised when the optional official Meshtastic SDK is unavailable."""


class _MeshtasticInterface(Protocol):
    def close(self) -> None: ...

    def sendData(  # noqa: N802 - official Meshtastic API name
        self,
        data: bytes,
        destination_id: int,
        **kwargs: object,
    ) -> object: ...


class _SerialFactory(Protocol):
    def __call__(
        self,
        device_path: str | None = None,
        **kwargs: object,
    ) -> _MeshtasticInterface: ...


class _TCPFactory(Protocol):
    def __call__(self, hostname: str, **kwargs: object) -> _MeshtasticInterface: ...


class _PortLister(Protocol):
    def __call__(self) -> Iterable[object]: ...


class _Publisher(Protocol):
    def subscribe(self, listener: Callable[..., None], topic_name: str) -> None: ...

    def unsubscribe(self, listener: Callable[..., None], topic_name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class _MeshtasticRuntime:
    serial_factory: _SerialFactory
    tcp_factory: _TCPFactory
    list_ports: _PortLister
    publisher: _Publisher
    private_app: int
    payload_limit: int
    background_priority: int
    reliable_priority: int
    disabled_channel_role: int


class MeshtasticConnectionGateway:
    """Own one explicitly opened local SDK connection across supported transports."""

    def __init__(self) -> None:
        self._interface: _MeshtasticInterface | None = None
        self._publisher: _Publisher | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._interface is not None

    def list_devices(self) -> tuple[MeshtasticDevice, ...]:
        """List cross-platform serial endpoints without opening a radio."""
        runtime = _load_runtime()
        devices: list[MeshtasticDevice] = []
        for port in runtime.list_ports():
            path = getattr(port, "device", None)
            if not isinstance(path, str) or not path:
                continue
            description = getattr(port, "description", None)
            label = (
                description
                if isinstance(description, str)
                and description
                and description.casefold() not in {"n/a", "unknown"}
                else path
            )
            is_usb = getattr(port, "vid", None) is not None
            devices.append(
                MeshtasticDevice(
                    path=path,
                    label=label,
                    connection_type=(
                        MeshtasticConnectionType.USB if is_usb else MeshtasticConnectionType.SERIAL
                    ),
                )
            )
        return tuple(sorted(devices, key=lambda device: device.path.casefold()))

    def discover(self, config: MeshtasticConnectionConfig) -> MeshtasticNodeChannels:
        """Open and retain the chosen connection, then inspect safe public metadata."""
        self.close()
        runtime = _load_runtime()
        try:
            if config.connection_type is MeshtasticConnectionType.NETWORK:
                interface = runtime.tcp_factory(
                    config.endpoint,
                    timeout=CONNECTION_TIMEOUT_SECONDS,
                )
            else:
                interface = runtime.serial_factory(
                    config.endpoint or None,
                    timeout=CONNECTION_TIMEOUT_SECONDS,
                )
        except Exception as error:
            raise TransportError(f"Could not connect to Meshtastic node: {error}") from error

        try:
            snapshot = MeshtasticNodeChannels(
                node_id=_read_node_id(interface),
                connection_type=config.connection_type,
                channels=_read_channels(interface, runtime.disabled_channel_role),
                endpoint=config.endpoint,
                node_name=_read_node_name(interface),
                firmware_version=_read_firmware_version(interface),
            )
            runtime.publisher.subscribe(self._on_connection_lost, CONNECTION_LOST_TOPIC)
        except Exception:
            interface.close()
            raise
        self._interface = interface
        self._publisher = runtime.publisher
        self._connected = True
        return snapshot

    def close(self) -> None:
        interface = self._interface
        publisher = self._publisher
        self._interface = None
        self._publisher = None
        self._connected = False
        if publisher is not None:
            publisher.unsubscribe(self._on_connection_lost, CONNECTION_LOST_TOPIC)
        if interface is not None:
            interface.close()

    def _on_connection_lost(
        self,
        interface: object | None = None,
        **_kwargs: object,
    ) -> None:
        if interface is None or interface is self._interface:
            self._connected = False


class SerialMeshtasticChannelDiscovery:
    """Explicitly inspect enabled channels on one serial-connected node."""

    def __init__(self, device: str | None = None) -> None:
        self.device = device

    def discover(self) -> MeshtasticNodeChannels:
        gateway = MeshtasticConnectionGateway()
        try:
            return gateway.discover(
                MeshtasticConnectionConfig(
                    MeshtasticConnectionType.SERIAL,
                    self.device or "",
                )
            )
        finally:
            gateway.close()


class MeshtasticTransport:
    """Send and receive SOLoRa frames through one serial Meshtastic node."""

    def __init__(
        self,
        interface: _MeshtasticInterface,
        publisher: _Publisher,
        *,
        private_app: int,
        payload_limit: int,
        background_priority: int,
        reliable_priority: int,
        channel_index: int = 0,
        channel_name: str | None = None,
        hop_limit: int | None = None,
    ) -> None:
        if payload_limit <= 0:
            raise ValueError("Meshtastic payload limit must be positive")
        if not 0 <= channel_index <= 7:
            raise ValueError("Meshtastic channel index must be between 0 and 7")
        if hop_limit is not None and not 0 <= hop_limit <= 7:
            raise ValueError("Meshtastic hop limit must be between 0 and 7")

        self._interface = interface
        self._publisher = publisher
        self._private_app = private_app
        self._payload_limit = min(payload_limit, MESHTASTIC_DATA_PAYLOAD_MAX)
        self._background_priority = background_priority
        self._reliable_priority = reliable_priority
        self._channel_index = channel_index
        self._channel_name = channel_name
        self._hop_limit = hop_limit
        self._receiver: FrameReceiver | None = None
        self._closed = False
        self._last_packet_id: int | None = None
        self._node_id = _read_node_id(interface)
        self._publisher.subscribe(self._on_receive, PRIVATE_APP_TOPIC)

    @classmethod
    def open_serial(
        cls,
        device: str | None = None,
        *,
        channel_index: int = 0,
        channel_name: str | None = None,
        hop_limit: int | None = None,
    ) -> MeshtasticTransport:
        """Open an official Meshtastic ``SerialInterface``."""
        runtime = _load_runtime()
        try:
            interface = runtime.serial_factory(device)
        except Exception as error:
            raise TransportError(f"Could not open Meshtastic serial device: {error}") from error
        try:
            _validate_channel(
                interface,
                channel_index=channel_index,
                channel_name=channel_name,
                disabled_role=runtime.disabled_channel_role,
            )
            return cls(
                interface,
                runtime.publisher,
                private_app=runtime.private_app,
                payload_limit=runtime.payload_limit,
                background_priority=runtime.background_priority,
                reliable_priority=runtime.reliable_priority,
                channel_index=channel_index,
                channel_name=channel_name,
                hop_limit=hop_limit,
            )
        except Exception:
            interface.close()
            raise

    @classmethod
    def open_network(
        cls,
        hostname: str,
        *,
        channel_index: int = 0,
        channel_name: str | None = None,
        hop_limit: int | None = None,
    ) -> MeshtasticTransport:
        """Open an official Meshtastic ``TCPInterface``."""
        runtime = _load_runtime()
        try:
            interface = runtime.tcp_factory(hostname)
        except Exception as error:
            raise TransportError(f"Could not open Meshtastic network node: {error}") from error
        try:
            _validate_channel(
                interface,
                channel_index=channel_index,
                channel_name=channel_name,
                disabled_role=runtime.disabled_channel_role,
            )
            return cls(
                interface,
                runtime.publisher,
                private_app=runtime.private_app,
                payload_limit=runtime.payload_limit,
                background_priority=runtime.background_priority,
                reliable_priority=runtime.reliable_priority,
                channel_index=channel_index,
                channel_name=channel_name,
                hop_limit=hop_limit,
            )
        except Exception:
            interface.close()
            raise

    @property
    def node_id(self) -> int:
        return self._node_id

    @property
    def last_packet_id(self) -> int | None:
        """Most recent Meshtastic packet ID accepted by the local SDK."""
        return self._last_packet_id

    @property
    def channel_index(self) -> int:
        return self._channel_index

    @property
    def channel_name(self) -> str | None:
        return self._channel_name

    def set_receiver(self, receiver: FrameReceiver) -> None:
        self._receiver = receiver

    def send(
        self,
        destination: int,
        payload: bytes,
        *,
        priority: TrafficPriority,
    ) -> None:
        if self._closed:
            raise TransportError("Meshtastic transport is closed")
        if not 0 < destination <= 0xFFFFFFFF:
            raise TransportError("Destination must fit in an unsigned 32-bit node ID")
        if len(payload) > self._payload_limit:
            raise TransportError(
                f"Payload is {len(payload)} bytes; Meshtastic limit is {self._payload_limit}"
            )
        if _queue_is_full(self._interface):
            raise TransportError("Meshtastic transmit queue is full")

        meshtastic_priority = (
            self._reliable_priority
            if priority is TrafficPriority.USER
            else self._background_priority
        )
        try:
            packet = self._interface.sendData(
                payload,
                destination,
                **{
                    "portNum": self._private_app,
                    "wantAck": destination != BROADCAST_NODE_ID,
                    "wantResponse": False,
                    "channelIndex": self._channel_index,
                    "hopLimit": self._hop_limit,
                    "priority": meshtastic_priority,
                },
            )
        except Exception as error:
            raise TransportError(f"Meshtastic send failed: {error}") from error

        packet_id = getattr(packet, "id", None)
        if not isinstance(packet_id, int) or isinstance(packet_id, bool) or packet_id == 0:
            raise TransportError("Meshtastic SDK did not return a valid packet ID")
        self._last_packet_id = packet_id

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._publisher.unsubscribe(self._on_receive, PRIVATE_APP_TOPIC)
        self._interface.close()

    def _on_receive(
        self,
        packet: object,
        interface: object | None = None,
        **_kwargs: object,
    ) -> None:
        if self._closed or (interface is not None and interface is not self._interface):
            return
        frame = _decode_inbound(
            packet,
            private_app=self._private_app,
            payload_limit=self._payload_limit,
            channel_index=self._channel_index,
        )
        if frame is not None and self._receiver is not None:
            self._receiver(frame)


def _decode_inbound(
    packet: object,
    *,
    private_app: int,
    payload_limit: int,
    channel_index: int,
) -> InboundFrame | None:
    if not isinstance(packet, Mapping):
        return None
    decoded = packet.get("decoded")
    if not isinstance(decoded, Mapping):
        return None
    portnum = decoded.get("portnum")
    if portnum not in (private_app, "PRIVATE_APP"):
        return None
    packet_channel = packet.get("channel", 0)
    if not _is_channel_index(packet_channel) or packet_channel != channel_index:
        return None

    source = packet.get("from")
    destination = packet.get("to")
    payload = decoded.get("payload")
    if not _is_node_id(source) or source == 0:
        return None
    if not _is_node_id(destination) or destination == 0:
        return None
    if not isinstance(payload, (bytes, bytearray)):
        return None
    raw_payload = bytes(payload)
    if len(raw_payload) > payload_limit:
        return None
    return InboundFrame(source=source, destination=destination, payload=raw_payload)


def _is_node_id(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFFFF


def _read_node_id(interface: _MeshtasticInterface) -> int:
    node_info = getattr(interface, "myInfo", None)
    node_id = getattr(node_info, "my_node_num", None)
    if not _is_node_id(node_id) or node_id == 0:
        raise TransportError("Meshtastic interface did not provide a valid local node ID")
    return node_id


def _read_node_name(interface: _MeshtasticInterface) -> str | None:
    getter = getattr(interface, "getLongName", None)
    if not callable(getter):
        return None
    name = getter()
    return name if isinstance(name, str) and name else None


def _read_firmware_version(interface: _MeshtasticInterface) -> str | None:
    metadata = getattr(interface, "metadata", None)
    version = getattr(metadata, "firmware_version", None)
    return version if isinstance(version, str) and version else None


def _read_channels(
    interface: _MeshtasticInterface,
    disabled_role: int,
) -> tuple[MeshtasticChannel, ...]:
    local_node = getattr(interface, "localNode", None)
    channels = getattr(local_node, "channels", None)
    if not isinstance(channels, (list, tuple)):
        raise TransportError("Meshtastic interface did not provide channel configuration")

    discovered: list[MeshtasticChannel] = []
    role_names = {0: "disabled", 1: "primary", 2: "secondary"}
    for channel in channels:
        index = getattr(channel, "index", None)
        role = getattr(channel, "role", None)
        settings = getattr(channel, "settings", None)
        name = getattr(settings, "name", None)
        if not _is_channel_index(index) or not isinstance(role, int) or isinstance(role, bool):
            continue
        if role == disabled_role:
            continue
        if not isinstance(name, str):
            continue
        discovered.append(MeshtasticChannel(index, name, role_names.get(role, f"role-{role}")))
    return tuple(sorted(discovered, key=lambda channel: channel.index))


def _validate_channel(
    interface: _MeshtasticInterface,
    *,
    channel_index: int,
    channel_name: str | None,
    disabled_role: int,
) -> None:
    channels = _read_channels(interface, disabled_role)
    selected = next((channel for channel in channels if channel.index == channel_index), None)
    if selected is None:
        raise TransportError(f"Meshtastic channel index {channel_index} is not enabled")
    if channel_name is not None and selected.name != channel_name:
        raise TransportError(
            "Meshtastic channel name/index no longer match; refresh and confirm the selection"
        )


def _is_channel_index(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 7


def _queue_is_full(interface: _MeshtasticInterface) -> bool:
    queue_status = getattr(interface, "queueStatus", None)
    free = getattr(queue_status, "free", None)
    return isinstance(free, int) and not isinstance(free, bool) and free <= 0


def _load_runtime() -> _MeshtasticRuntime:
    try:
        serial_module = import_module("meshtastic.serial_interface")
        tcp_module = import_module("meshtastic.tcp_interface")
        channel_module = import_module("meshtastic.protobuf.channel_pb2")
        mesh_module = import_module("meshtastic.protobuf.mesh_pb2")
        portnums_module = import_module("meshtastic.protobuf.portnums_pb2")
        publisher = import_module("pubsub").pub
        list_ports = import_module("serial.tools.list_ports").comports
    except (ImportError, AttributeError) as error:
        raise MeshtasticUnavailableError(
            "Meshtastic support is not installed; run 'make setup-radio'"
        ) from error

    mesh_packet = mesh_module.MeshPacket
    priorities = mesh_packet.Priority
    constants = mesh_module.Constants
    portnums = portnums_module.PortNum
    return _MeshtasticRuntime(
        serial_factory=cast(_SerialFactory, serial_module.SerialInterface),
        tcp_factory=cast(_TCPFactory, tcp_module.TCPInterface),
        list_ports=cast(_PortLister, list_ports),
        publisher=cast(_Publisher, publisher),
        private_app=int(portnums.PRIVATE_APP),
        payload_limit=int(constants.DATA_PAYLOAD_LEN),
        background_priority=int(priorities.BACKGROUND),
        reliable_priority=int(priorities.RELIABLE),
        disabled_channel_role=int(channel_module.Channel.Role.DISABLED),
    )
