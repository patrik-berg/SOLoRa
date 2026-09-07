"""Tests for transport configuration and the diagnostic CLI."""

from typing import cast

import pytest

from solora.adapters.transport import factory
from solora.adapters.transport.factory import (
    TransportKind,
    TransportSettings,
    create_transport,
)
from solora.adapters.transport.in_memory import InMemoryTransport
from solora.transport_cli import main


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOLORA_TRANSPORT", "meshtastic-serial")
    monkeypatch.setenv("SOLORA_MESHTASTIC_DEVICE", "/dev/tty.usbmodem-test")
    monkeypatch.setenv("SOLORA_MESHTASTIC_CHANNEL", "2")
    monkeypatch.setenv("SOLORA_MESHTASTIC_HOP_LIMIT", "3")

    settings = TransportSettings.from_environment()

    assert settings == TransportSettings(
        kind=TransportKind.MESHTASTIC_SERIAL,
        serial_device="/dev/tty.usbmodem-test",
        channel_index=2,
        hop_limit=3,
    )


def test_factory_creates_in_memory_transport() -> None:
    transport = create_transport(TransportSettings(), node_id=0xA)

    assert isinstance(transport, InMemoryTransport)
    assert transport.node_id == 0xA


def test_factory_delegates_serial_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, int, int | None]] = []
    marker = cast(InMemoryTransport, create_transport(TransportSettings(), node_id=1))

    def open_serial(
        device: str | None,
        *,
        channel_index: int,
        hop_limit: int | None,
    ) -> InMemoryTransport:
        calls.append((device, channel_index, hop_limit))
        return marker

    monkeypatch.setattr(factory.MeshtasticTransport, "open_serial", open_serial)
    result = create_transport(
        TransportSettings(
            kind=TransportKind.MESHTASTIC_SERIAL,
            serial_device="/dev/test",
            channel_index=4,
            hop_limit=5,
        )
    )

    assert result is marker
    assert calls == [("/dev/test", 4, 5)]


def test_cli_selects_in_memory(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--transport", "in-memory", "--node-id", "0xa"]) == 0
    assert "Transport ready: in-memory, node=0x0000000a" in capsys.readouterr().out


def test_cli_rejects_unpaired_send_arguments() -> None:
    with pytest.raises(SystemExit):
        main(["--send-to", "2"])
