"""Explicit, silent-by-default Meshtastic connection and channel configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol

from solora.domain.meshtastic_settings import (
    RECOMMENDED_CHANNEL_NAME,
    MeshtasticChannel,
    MeshtasticChannelSelection,
    MeshtasticConnectionConfig,
    MeshtasticDevice,
    MeshtasticNodeChannels,
    MeshtasticSavedConnection,
)


class MeshtasticGateway(Protocol):
    """Discover endpoints and own an explicitly opened SDK connection."""

    @property
    def connected(self) -> bool: ...

    def list_devices(self) -> tuple[MeshtasticDevice, ...]: ...

    def discover(self, config: MeshtasticConnectionConfig) -> MeshtasticNodeChannels: ...

    def close(self) -> None: ...


class ChannelSettingsRepository(Protocol):
    """Persist the user-confirmed local channel binding."""

    def get_channel_selection(self) -> MeshtasticChannelSelection | None: ...

    def save_channel_selection(self, selection: MeshtasticChannelSelection) -> None: ...

    def get_connection(self) -> MeshtasticSavedConnection | None: ...

    def save_connection(self, connection: MeshtasticSavedConnection) -> None: ...


class ChannelSelectionError(ValueError):
    """Raised when a requested channel is unavailable or has changed."""


@dataclass(frozen=True, slots=True)
class MeshtasticSettingsStatus:
    """Current discovery and selection state for the settings UI."""

    connected: bool
    node_id: int | None
    connection_type: str | None
    channels: tuple[MeshtasticChannel, ...]
    devices: tuple[MeshtasticDevice, ...]
    connection: MeshtasticConnectionConfig | None
    selection: MeshtasticChannelSelection | None
    selection_valid: bool
    recommended_channel_index: int | None
    node_name: str | None
    firmware_version: str | None
    last_contact: datetime | None
    error: str | None


class MeshtasticSettingsController:
    """Cache explicit discovery without creating idle radio traffic."""

    def __init__(self, gateway: MeshtasticGateway) -> None:
        self._gateway = gateway
        self._snapshot: MeshtasticNodeChannels | None = None
        self._devices: tuple[MeshtasticDevice, ...] = ()
        self._discovery_error: str | None = None
        self._lock = Lock()

    def status(self, repository: ChannelSettingsRepository) -> MeshtasticSettingsStatus:
        """Read cached state; never contacts the radio."""
        with self._lock:
            return self._status(repository)

    def refresh(self, repository: ChannelSettingsRepository) -> MeshtasticSettingsStatus:
        """Reconnect to the saved endpoint only after an explicit user action."""
        saved = repository.get_connection()
        if saved is None:
            with self._lock:
                self._discovery_error = "Choose a Meshtastic connection first"
                return self._status(repository)
        return self.test_connection(repository, saved.config)

    def refresh_devices(
        self,
        repository: ChannelSettingsRepository,
    ) -> MeshtasticSettingsStatus:
        """Refresh local serial endpoints without opening them or using radio airtime."""
        with self._lock:
            try:
                self._devices = self._gateway.list_devices()
                self._discovery_error = None
            except Exception as discovery_error:
                self._discovery_error = str(discovery_error) or "Meshtastic discovery failed"
            return self._status(repository)

    def test_connection(
        self,
        repository: ChannelSettingsRepository,
        config: MeshtasticConnectionConfig,
    ) -> MeshtasticSettingsStatus:
        """Open the selected endpoint, read node details, and retain the live connection."""
        with self._lock:
            previous = repository.get_connection()
            try:
                snapshot = self._gateway.discover(config)
            except Exception as discovery_error:
                self._snapshot = None
                self._discovery_error = str(discovery_error) or "Meshtastic connection failed"
                repository.save_connection(
                    MeshtasticSavedConnection(
                        config=config,
                        node_id=previous.node_id
                        if previous and previous.config == config
                        else None,
                        node_name=(
                            previous.node_name if previous and previous.config == config else None
                        ),
                        firmware_version=(
                            previous.firmware_version
                            if previous and previous.config == config
                            else None
                        ),
                        last_contact=(
                            previous.last_contact
                            if previous and previous.config == config
                            else None
                        ),
                    )
                )
            else:
                self._snapshot = snapshot
                self._discovery_error = None
                repository.save_connection(
                    MeshtasticSavedConnection(
                        config=config,
                        node_id=snapshot.node_id,
                        node_name=snapshot.node_name,
                        firmware_version=snapshot.firmware_version,
                        last_contact=datetime.now(UTC),
                    )
                )
            return self._status(repository)

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
            return self._status(repository, selection=selection)

    def close(self) -> None:
        self._gateway.close()

    def _status(
        self,
        repository: ChannelSettingsRepository,
        *,
        selection: MeshtasticChannelSelection | None = None,
    ) -> MeshtasticSettingsStatus:
        if selection is None:
            selection = repository.get_channel_selection()
        saved_connection = repository.get_connection()
        snapshot = self._snapshot
        if snapshot is None:
            status_error = self._discovery_error
            if status_error is None and selection is not None:
                status_error = "Saved channel has not been verified against a connected node"
            return MeshtasticSettingsStatus(
                connected=False,
                node_id=saved_connection.node_id if saved_connection else None,
                connection_type=(
                    saved_connection.config.connection_type if saved_connection else None
                ),
                channels=(),
                devices=self._devices,
                connection=saved_connection.config if saved_connection else None,
                selection=selection,
                selection_valid=False,
                recommended_channel_index=None,
                node_name=saved_connection.node_name if saved_connection else None,
                firmware_version=(saved_connection.firmware_version if saved_connection else None),
                last_contact=saved_connection.last_contact if saved_connection else None,
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
        if not self._gateway.connected:
            error = "Connection to the configured Meshtastic node was lost"

        return MeshtasticSettingsStatus(
            connected=self._gateway.connected,
            node_id=snapshot.node_id,
            connection_type=snapshot.connection_type,
            channels=snapshot.channels,
            devices=self._devices,
            connection=saved_connection.config if saved_connection else None,
            selection=selection,
            selection_valid=valid,
            recommended_channel_index=recommended,
            node_name=snapshot.node_name,
            firmware_version=snapshot.firmware_version,
            last_contact=saved_connection.last_contact if saved_connection else None,
            error=error,
        )
