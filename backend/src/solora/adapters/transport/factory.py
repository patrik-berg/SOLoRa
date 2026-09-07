"""Configuration and construction for selectable SOLoRa transports."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from solora.adapters.transport.in_memory import InMemoryNetwork
from solora.adapters.transport.meshtastic import MeshtasticTransport
from solora.application.transport_ports import Transport

__all__ = ["MeshtasticTransport", "TransportKind", "TransportSettings", "create_transport"]


class TransportKind(StrEnum):
    IN_MEMORY = "in-memory"
    MESHTASTIC_SERIAL = "meshtastic-serial"


@dataclass(frozen=True, slots=True)
class TransportSettings:
    kind: TransportKind = TransportKind.IN_MEMORY
    serial_device: str | None = None
    channel_index: int = 0
    channel_name: str | None = None
    hop_limit: int | None = None

    @classmethod
    def from_environment(cls) -> TransportSettings:
        """Read the transport selection without opening hardware."""
        kind = TransportKind(os.getenv("SOLORA_TRANSPORT", TransportKind.IN_MEMORY))
        device = os.getenv("SOLORA_MESHTASTIC_DEVICE") or None
        channel_index = int(os.getenv("SOLORA_MESHTASTIC_CHANNEL", "0"))
        channel_name = os.getenv("SOLORA_MESHTASTIC_CHANNEL_NAME") or None
        hop_value = os.getenv("SOLORA_MESHTASTIC_HOP_LIMIT")
        return cls(
            kind=kind,
            serial_device=device,
            channel_index=channel_index,
            channel_name=channel_name,
            hop_limit=int(hop_value) if hop_value else None,
        )


def create_transport(
    settings: TransportSettings,
    *,
    node_id: int = 1,
    network: InMemoryNetwork | None = None,
) -> Transport:
    """Create the configured adapter behind the common transport port."""
    if settings.kind is TransportKind.MESHTASTIC_SERIAL:
        return MeshtasticTransport.open_serial(
            settings.serial_device,
            channel_index=settings.channel_index,
            channel_name=settings.channel_name,
            hop_limit=settings.hop_limit,
        )
    return (network or InMemoryNetwork()).connect(node_id)
