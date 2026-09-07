# SOLoRa

SOLoRa is a local-first communication application intended to combine a small web forum with Meshtastic transport. The repository is currently in **Phase 0: development foundation**. Forum, database, radio transport, updater, and production release behavior are deliberately not implemented yet.

## Chosen stack

- Python 3.12 and FastAPI for the local HTTP service
- SQLite with SQLAlchemy and Alembic for the future persistence layer
- Server-rendered HTML with small progressive enhancements for the first UI
- Meshtastic behind a transport interface so hardware is replaceable in tests
- pytest, Ruff, and mypy for automated verification
- `uv` for Python and dependency management

## Development

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
make setup
make check
make dev
```

`make dev` starts the scaffold server at `http://127.0.0.1:8000`. Its only endpoint is `GET /health`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [PROTOCOL.md](PROTOCOL.md), and [ROADMAP.md](ROADMAP.md) before implementing product features.
