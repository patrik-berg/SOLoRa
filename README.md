# SOLoRa

SOLoRa is a local-first communication application intended to combine a small web forum with Meshtastic transport. The repository is currently in **Phase 0: development foundation**. Forum, database, radio transport, updater, and production release behavior are deliberately not implemented yet.

## Chosen stack

- Python 3.12 and FastAPI for the local HTTP service
- SQLite with SQLAlchemy and Alembic for the future persistence layer
- React 19, TypeScript, and Vite for the local web interface
- Meshtastic behind a transport interface so hardware is replaceable in tests
- pytest, Ruff, and mypy for automated verification
- `uv` for Python and dependency management

## Development

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), Node.js 24, and pnpm 11, then run:

```sh
make setup
make check
make dev
```

Run `make dev-backend` and `make dev-frontend` in separate terminals. The backend starts at `http://127.0.0.1:8000`; the frontend starts at `http://127.0.0.1:5173`. No forum or radio functionality exists yet.

See [ARCHITECTURE.md](ARCHITECTURE.md), [PROTOCOL.md](PROTOCOL.md), and [ROADMAP.md](ROADMAP.md) before implementing product features.
