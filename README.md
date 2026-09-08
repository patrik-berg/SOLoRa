# SOLoRa

SOLoRa is a local-first communication application. **Phase 1** provides a small forum that runs entirely on one computer: create threads, open them, and publish posts that remain in a local SQLite database. **Phase 2** adds binary two-node transport, durable retry, deduplication, explicit hardware-independent forum repair, and an initial USB/serial Meshtastic adapter. Accounts, automatic synchronization scheduling, and automatic releases are not implemented yet.

Current application version: `0.1.0` (local MVP; not a published stable release).

Phase 3 will add an installed desktop control window for service status, web addresses, interface/port changes, opening the browser, Hide/Quit, and startup preferences. The forum and advanced settings stay in the web app. A separate headless mode will support servers and Raspberry Pi without a desktop. This is planned, not yet available; see the [desktop and headless delivery design](docs/PHASE3_DESKTOP_DELIVERY.md).

Planned distributions are **SOLoRa Desktop** for Windows/macOS, **SOLoRa Server** installed on existing Linux/Raspberry Pi OS (Pi 4/5, preferably `.deb`), and **SOLoRa Appliance** as a flashable headless SD image for Pi Zero 2 W. All share the same core. Hardware never selects `CLIENT`, `PRIMARY`, or `BACKUP`; roles remain explicit. Zero 2 W Primary/Backup performance and robustness are targets awaiting physical validation. The appliance will include automatic startup, browser setup, and `solora-config` recovery without a desktop.

## Chosen stack

- Python 3.12 and FastAPI for the local HTTP service
- SQLite with SQLAlchemy and Alembic for persistence
- React 19, TypeScript, and Vite for the local web interface
- Meshtastic behind a transport interface so hardware is replaceable in tests
- pytest, Ruff, and mypy for automated verification
- `uv` for Python and dependency management

## Start SOLoRa on macOS

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), Node.js 24, and pnpm 11. From the repository root, run:

```sh
make setup
make run
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the server with `Ctrl+C`. Forum data is stored in `data/solora.db` and survives restarts. Back up that file while SOLoRa is stopped.

For development, run `make dev-backend` and `make dev-frontend` in separate terminals, then open [http://127.0.0.1:5173](http://127.0.0.1:5173). Run `make check` before committing; it performs formatting checks, linting, type checks, tests, and production builds.

## Test two virtual nodes

After `make setup`, run:

```sh
make demo-two-nodes
```

The demo creates two temporary SQLite databases, drops Node A's first POST, advances the retry clock, delivers the resend to Node B, processes `COMMIT_ACK`, and replays the POST to prove that no duplicate is stored. It requires no radio hardware and leaves no project data behind.

Automated integration tests additionally start two nodes with different local forum data, take one node offline, drop a repair packet after reconnect, and verify bidirectional convergence and idempotent re-sync. Repair is initiated explicitly through `SyncNode.request_sync(peer_node_id)`; normal idle state remains silent.

## Select a transport

The default is hardware-free:

```sh
SOLORA_TRANSPORT=in-memory make transport-info
```

The normal app includes the official Meshtastic SDK. Start SOLoRa, open **Systeminställningar → Meshtastic**, and complete the guided flow:

1. Choose **USB**, **Serial**, or **Network**.
2. Refresh and select a serial device (including Windows `COM` ports), or enter a network hostname/IP.
3. Test and save the connection.
4. Confirm the channel; `solora-link` is recommended when present.

No environment variables or manual config editing are required. The fields below remain available only for developer diagnostics:

```sh
SOLORA_MESHTASTIC_DEVICE=/dev/cu.usbmodem0001 \
SOLORA_MESHTASTIC_CHANNEL=3 \
SOLORA_MESHTASTIC_CHANNEL_NAME=solora-link \
make transport-radio
```

The saved configuration includes connection type, endpoint, last known public node metadata, node ID, channel name, and that node's local channel index. A missing node or changed channel requires explicit reconfirmation. SOLoRa does not read, expose, or persist the channel PSK.

## Configure system identity

Open **Systeminställningar → System** to set the local display name and explicit role. `Client` is active; `Primary server` and `Backup server` are stored for test environments but remain experimental until their runtime behavior is implemented. Changing role requires a visible confirmation. The same page shows browser-accessible diagnostics for system identity, Meshtastic connection, selected channel, and app/protocol versions.

System name, system role, and Meshtastic Node ID are deliberately separate. `SOL1` is only a common display name and has no special behavior. A Primary is defined by `system_role = PRIMARY` and identified to other nodes by its Meshtastic Node ID, not its name.

Programmatic construction uses `TransportSettings.from_environment()` and `create_transport()`. Supported values for `SOLORA_TRANSPORT` are `in-memory`, `meshtastic-serial`, and `meshtastic-network`. The CLI only verifies transport construction; it does not start forum synchronization.

See [the two-radio hardware procedure](docs/MESHTASTIC_HARDWARE_TEST.md) before connecting physical nodes.

See [ARCHITECTURE.md](ARCHITECTURE.md), [PROTOCOL.md](PROTOCOL.md), and [ROADMAP.md](ROADMAP.md) before implementing product features.
