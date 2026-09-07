# SOLoRa

SOLoRa is a local-first communication application. **Phase 1** provides a small forum that runs entirely on one computer: create threads, open them, and publish posts that remain in a local SQLite database. **Phase 2** adds binary two-node transport, durable retry, deduplication, explicit hardware-independent forum repair, and an initial USB/serial Meshtastic adapter. **Phase 3** now has a manual beta packaging and GitHub prerelease foundation. Accounts, automatic synchronization scheduling, native installers, and the in-client updater are not implemented yet.

Current application version: `0.1.0` (local MVP; not a published stable release).

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

Install the optional official Meshtastic SDK before opening a USB radio:

```sh
make setup-radio
SOLORA_MESHTASTIC_DEVICE=/dev/cu.usbmodem0001 make transport-radio
```

Programmatic construction uses `TransportSettings.from_environment()` and `create_transport()`. Supported values for `SOLORA_TRANSPORT` are `in-memory` and `meshtastic-serial`; serial settings also accept `SOLORA_MESHTASTIC_DEVICE`, `SOLORA_MESHTASTIC_CHANNEL`, and `SOLORA_MESHTASTIC_HOP_LIMIT`.

See [the two-radio hardware procedure](docs/MESHTASTIC_HARDWARE_TEST.md) before connecting physical nodes.

## Publish a beta

After the beta workflow is merged to `main`, open **Actions → Beta release → Run workflow**, enter a base such as `0.2.0`, enable the prerelease confirmation, and run it from `main`. The workflow repeats `make check`, chooses the next available `v0.2.0-beta.N`, builds a portable bundle and SHA-256 update manifest, signs their GitHub provenance, and creates a GitHub prerelease. It cannot publish Stable.

The portable bundle is an early cross-platform test artifact requiring Python 3.12, not a signed native installer. Its included `BETA_README.md` explains local startup and provenance verification. Native installers, updater trust/rollback, and **Install beta** remain later Phase 3 work.

See [ARCHITECTURE.md](ARCHITECTURE.md), [PROTOCOL.md](PROTOCOL.md), and [ROADMAP.md](ROADMAP.md) before implementing product features.
