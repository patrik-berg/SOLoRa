"""Deterministic, hardware-free transport for tests and local simulations."""

from dataclasses import dataclass

from solora.application.transport_ports import (
    FrameReceiver,
    InboundFrame,
    TrafficPriority,
    TransportError,
)
from solora.domain.protocol import MESHTASTIC_DATA_PAYLOAD_MAX


@dataclass(frozen=True, slots=True)
class Transmission:
    """One attempted in-memory transmission."""

    frame: InboundFrame
    priority: TrafficPriority
    delivered: bool


class InMemoryNetwork:
    """Connect virtual nodes and optionally drop deterministic frames."""

    def __init__(self) -> None:
        self._transports: dict[int, InMemoryTransport] = {}
        self._drop_budget = 0
        self.transmissions: list[Transmission] = []

    def connect(self, node_id: int) -> "InMemoryTransport":
        if not 0 < node_id <= 0xFFFFFFFF:
            raise ValueError("Node ID must fit in an unsigned 32-bit integer")
        if node_id in self._transports:
            raise ValueError(f"Node {node_id} is already connected")
        transport = InMemoryTransport(node_id, self)
        self._transports[node_id] = transport
        return transport

    def drop_next(self, count: int = 1) -> None:
        """Silently lose the next frames, as a radio network can."""
        if count < 1:
            raise ValueError("Drop count must be positive")
        self._drop_budget += count

    def transmit(
        self,
        frame: InboundFrame,
        *,
        priority: TrafficPriority,
    ) -> None:
        receiver = self._transports.get(frame.destination)
        delivered = (
            self._drop_budget == 0 and receiver is not None and receiver.receiver is not None
        )
        if self._drop_budget:
            self._drop_budget -= 1
        self.transmissions.append(Transmission(frame, priority, delivered))
        if delivered and receiver is not None and receiver.receiver is not None:
            receiver.receiver(frame)

    def replay(self, transmission: Transmission) -> None:
        """Deliver a captured frame again to test idempotency."""
        receiver = self._transports.get(transmission.frame.destination)
        if receiver is not None and receiver.receiver is not None:
            receiver.receiver(transmission.frame)


class InMemoryTransport:
    """One virtual endpoint on an :class:`InMemoryNetwork`."""

    def __init__(self, node_id: int, network: InMemoryNetwork) -> None:
        self._node_id = node_id
        self._network = network
        self.receiver: FrameReceiver | None = None

    @property
    def node_id(self) -> int:
        return self._node_id

    def set_receiver(self, receiver: FrameReceiver) -> None:
        self.receiver = receiver

    def send(
        self,
        destination: int,
        payload: bytes,
        *,
        priority: TrafficPriority,
    ) -> None:
        if len(payload) > MESHTASTIC_DATA_PAYLOAD_MAX:
            raise TransportError("Payload exceeds Meshtastic Data.payload limit")
        self._network.transmit(
            InboundFrame(self.node_id, destination, payload),
            priority=priority,
        )
