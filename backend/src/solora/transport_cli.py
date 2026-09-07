"""Small transport diagnostic CLI for virtual or serial Meshtastic adapters."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from solora.adapters.transport.factory import (
    TransportKind,
    TransportSettings,
    create_transport,
)
from solora.adapters.transport.meshtastic import MeshtasticTransport
from solora.application.transport_ports import InboundFrame, TrafficPriority, TransportError


def _node_id(value: str) -> int:
    parsed = int(value, 0)
    if not 0 < parsed <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("node ID must be between 1 and 0xffffffff")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Inspect a SOLoRa transport")
    result.add_argument(
        "--transport",
        choices=[kind.value for kind in TransportKind],
        default=os.getenv("SOLORA_TRANSPORT", TransportKind.IN_MEMORY),
    )
    result.add_argument("--device", default=os.getenv("SOLORA_MESHTASTIC_DEVICE"))
    result.add_argument("--node-id", type=_node_id, default=1)
    result.add_argument("--channel", type=int, default=0)
    result.add_argument("--channel-name", default=os.getenv("SOLORA_MESHTASTIC_CHANNEL_NAME"))
    result.add_argument("--hop-limit", type=int)
    result.add_argument("--send-to", type=_node_id)
    result.add_argument("--payload-hex")
    result.add_argument("--listen", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (args.send_to is None) != (args.payload_hex is None):
        parser().error("--send-to and --payload-hex must be used together")

    settings = TransportSettings(
        kind=TransportKind(args.transport),
        serial_device=args.device,
        channel_index=args.channel,
        channel_name=args.channel_name,
        hop_limit=args.hop_limit,
    )
    transport = None
    try:
        transport = create_transport(settings, node_id=args.node_id)
        transport.set_receiver(_print_frame)
        print(f"Transport ready: {settings.kind.value}, node=0x{transport.node_id:08x}")
        if args.payload_hex is not None and args.send_to is not None:
            transport.send(
                args.send_to,
                bytes.fromhex(args.payload_hex),
                priority=TrafficPriority.USER,
            )
            print(f"Payload accepted for 0x{args.send_to:08x}")
        if args.listen:
            input("Listening; press Enter to stop.\n")
    except (TransportError, ValueError) as error:
        print(f"Transport error: {error}")
        return 1
    finally:
        if isinstance(transport, MeshtasticTransport):
            transport.close()
    return 0


def _print_frame(frame: InboundFrame) -> None:
    print(
        f"RX source=0x{frame.source:08x} destination=0x{frame.destination:08x} "
        f"payload={frame.payload.hex()}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
