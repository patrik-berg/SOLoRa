"""Meshtastic channel metadata safe to expose outside the transport adapter."""

from dataclasses import dataclass

RECOMMENDED_CHANNEL_NAME = "solora-link"


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


@dataclass(frozen=True, slots=True)
class MeshtasticChannelSelection:
    """A user-confirmed channel bound to one node and local slot."""

    node_id: int
    channel_index: int
    channel_name: str
