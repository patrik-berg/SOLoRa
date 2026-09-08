# Meshtastic Two-Radio Test

This procedure validates the thin serial transport only. It does not enable full forum synchronization, fragmentation, presence, or SOL1 behavior.

## Prerequisites

- Two USB-connected Meshtastic nodes running compatible current firmware.
- Both radios configured for the same region, modem preset, channel, and PSK.
- No Meshtastic desktop/mobile client holding either serial port open.
- Python dependencies installed with `make setup-radio`.

Before the CLI checks, use **Systeminställningar → Meshtastic** to refresh devices, select USB/Serial or Network, test the connection, verify node name/ID/firmware, and confirm the channel. Disconnect the node and verify that local status changes to offline without presenting this as mesh reachability.

List serial ports on macOS:

```sh
.venv/bin/python -m serial.tools.list_ports
```

Read each node number separately, replacing the device path:

```sh
.venv/bin/meshtastic --port /dev/cu.usbmodemNODE_A --info
.venv/bin/meshtastic --port /dev/cu.usbmodemNODE_B --info
```

Record each hexadecimal node number, then close the commands so SOLoRa can open the ports.
Record the exact local channel index on each node. The shared `solora-link` channel may use different indices on A and B; never assume they match.

## Send A → B

In terminal B, start the receiver:

```sh
.tools/bin/uv run --extra radio python -m solora.transport_cli \
  --transport meshtastic-serial \
  --device /dev/cu.usbmodemNODE_B \
  --channel CHANNEL_INDEX_B \
  --channel-name solora-link \
  --listen
```

In terminal A, send the canonical v1 POST fixture. Replace `0xBBBBBBBB` with Node B's number:

```sh
.tools/bin/uv run --extra radio python -m solora.transport_cli \
  --transport meshtastic-serial \
  --device /dev/cu.usbmodemNODE_A \
  --channel CHANNEL_INDEX_A \
  --channel-name solora-link \
  --send-to 0xBBBBBBBB \
  --payload-hex 110102030405060708090a0b0c0000000000000000000000000000002a68656a \
  --listen
```

Terminal B must print the exact payload with Node A as `source` and Node B as `destination`. A Meshtastic routing ACK must not appear as an `RX` SOLoRa frame. Press Enter in both terminals to close cleanly.

Also send a `PRIVATE_APP` payload on another configured channel. SOLoRa must ignore it. Rename, remove, or move the selected channel and verify that reopening the adapter fails with a channel-binding error until the new local index and exact name are confirmed.

## Reverse and failure checks

Repeat with the radio roles reversed to verify both serial paths. Then disconnect Node B and send again from A. The CLI must report a local queue/serial result without claiming a SOLoRa `COMMIT_ACK`; routing delivery and durable application commit are intentionally separate.

Record firmware versions, SDK version, region/preset, channel utilization, packet IDs, observed latency, and any routing errors. Do not mark physical transport validated until both directions pass. Run `make demo-two-nodes` afterward to reconfirm durable retry and deduplication independently of hardware.
