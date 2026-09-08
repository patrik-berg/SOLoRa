"""Meshtastic connection metadata safe to expose outside infrastructure."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

RECOMMENDED_CHANNEL_NAME = "solora-link"


class MeshtasticConnectionType(StrEnum):
    USB = "usb"
    SERIAL = "serial"
    NETWORK = "network"


@dataclass(frozen=True, slots=True)
class MeshtasticDevice:
    """One discovered cross-platform serial endpoint."""

    path: str
    label: str
    connection_type: MeshtasticConnectionType


@dataclass(frozen=True, slots=True)
class MeshtasticConnectionConfig:
    """User-selected local connection, containing no credentials."""

    connection_type: MeshtasticConnectionType
    endpoint: str


@dataclass(frozen=True, slots=True)
class MeshtasticChannel:
    """One enabled local channel without its PSK or other secrets."""

    index: int
    name: str
    role: str

    @property
    def display_name(self) -> str:
        return self.name or "Primary"


@dataclass(frozen=True, slots=True)
class MeshtasticNodeChannels:
    """Public connection metadata discovered from one local radio."""

    node_id: int
    connection_type: str
    channels: tuple[MeshtasticChannel, ...]
    endpoint: str = ""
    node_name: str | None = None
    firmware_version: str | None = None


@dataclass(frozen=True, slots=True)
class MeshtasticChannelSelection:
    """A user-confirmed channel bound to one node and local slot."""

    node_id: int
    channel_index: int
    channel_name: str


@dataclass(frozen=True, slots=True)
class MeshtasticSavedConnection:
    """Persisted connection choice and last successful public node metadata."""

    config: MeshtasticConnectionConfig
    node_id: int | None = None
    node_name: str | None = None
    firmware_version: str | None = None
    last_contact: datetime | None = None
