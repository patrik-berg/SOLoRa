"""Explicit, silent-by-default Meshtastic channel configuration."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from solora.domain.meshtastic_settings import (
    RECOMMENDED_CHANNEL_NAME,
    MeshtasticChannel,
    MeshtasticChannelSelection,
    MeshtasticNodeChannels,
)


class ChannelDiscovery(Protocol):
    """Read public channel metadata from a connected local node."""

    def discover(self) -> MeshtasticNodeChannels: ...


class ChannelSettingsRepository(Protocol):
    """Persist the user-confirmed local channel binding."""

    def get_channel_selection(self) -> MeshtasticChannelSelection | None: ...

    def save_channel_selection(self, selection: MeshtasticChannelSelection) -> None: ...


class ChannelSelectionError(ValueError):
    """Raised when a requested channel is unavailable or has changed."""


@dataclass(frozen=True, slots=True)
class MeshtasticSettingsStatus:
    """Current discovery and selection state for the settings UI."""

    connected: bool
    node_id: int | None
    connection_type: str | None
    channels: tuple[MeshtasticChannel, ...]
    selection: MeshtasticChannelSelection | None
    selection_valid: bool
    recommended_channel_index: int | None
    error: str | None


class MeshtasticSettingsController:
    """Cache explicit discovery without creating idle radio traffic."""

    def __init__(self, discovery: ChannelDiscovery) -> None:
        self._discovery = discovery
        self._snapshot: MeshtasticNodeChannels | None = None
        self._discovery_error: str | None = None
        self._lock = Lock()

    def status(self, repository: ChannelSettingsRepository) -> MeshtasticSettingsStatus:
        """Read cached state; never contacts the radio."""
        with self._lock:
            return self._status(repository.get_channel_selection())

    def refresh(self, repository: ChannelSettingsRepository) -> MeshtasticSettingsStatus:
        """Discover channels only after an explicit user action."""
        with self._lock:
            try:
                self._snapshot = self._discovery.discover()
                self._discovery_error = None
            except Exception as discovery_error:
                self._snapshot = None
                self._discovery_error = str(discovery_error) or "Meshtastic discovery failed"
            return self._status(repository.get_channel_selection())

    def select(
        self,
        repository: ChannelSettingsRepository,
        *,
        channel_index: int,
        channel_name: str,
    ) -> MeshtasticSettingsStatus:
        """Persist an exact node/name/index binding from the latest discovery."""
        with self._lock:
            if self._snapshot is None:
                raise ChannelSelectionError("Refresh Meshtastic channels before selecting one")
            channel = next(
                (
                    candidate
                    for candidate in self._snapshot.channels
                    if candidate.index == channel_index and candidate.name == channel_name
                ),
                None,
            )
            if channel is None:
                raise ChannelSelectionError(
                    "The selected channel no longer matches the connected node; refresh and confirm"
                )
            selection = MeshtasticChannelSelection(
                node_id=self._snapshot.node_id,
                channel_index=channel.index,
                channel_name=channel.name,
            )
            repository.save_channel_selection(selection)
            return self._status(selection)

    def _status(
        self,
        selection: MeshtasticChannelSelection | None,
    ) -> MeshtasticSettingsStatus:
        snapshot = self._snapshot
        if snapshot is None:
            status_error = self._discovery_error
            if status_error is None and selection is not None:
                status_error = "Saved channel has not been verified against a connected node"
            return MeshtasticSettingsStatus(
                connected=False,
                node_id=None,
                connection_type=None,
                channels=(),
                selection=selection,
                selection_valid=False,
                recommended_channel_index=None,
                error=status_error,
            )

        recommended = next(
            (
                channel.index
                for channel in snapshot.channels
                if channel.name.casefold() == RECOMMENDED_CHANNEL_NAME
            ),
            None,
        )
        error: str | None = None
        valid = False
        if selection is None:
            error = "Choose and confirm a SOLoRa channel"
        elif selection.node_id != snapshot.node_id:
            error = "The connected Meshtastic node differs from the saved channel selection"
        elif not any(
            channel.index == selection.channel_index and channel.name == selection.channel_name
            for channel in snapshot.channels
        ):
            error = "The saved channel was removed, renamed, or moved; confirm a channel again"
        else:
            valid = True

        return MeshtasticSettingsStatus(
            connected=True,
            node_id=snapshot.node_id,
            connection_type=snapshot.connection_type,
            channels=snapshot.channels,
            selection=selection,
            selection_valid=valid,
            recommended_channel_index=recommended,
            error=error,
        )
