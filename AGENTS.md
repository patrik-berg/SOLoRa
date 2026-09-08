# Repository Guidelines

## Project Structure & Module Organization

Keep the root limited to project-wide configuration and documentation. The repository is organized as follows:

- `backend/src/solora/` contains the FastAPI API, domain code, and adapters.
- `frontend/src/` contains the React/TypeScript client; keep UI tests beside components.
- `protocol/` contains protocol design notes, schemas, and byte-level fixtures.
- `tests/` contains cross-component and integration tests; component-local unit tests may live beside their source.
- `.github/workflows/` contains CI and automation definitions.
- `ARCHITECTURE.md`, `PROTOCOL.md`, and `ROADMAP.md` document system design, wire behavior, and planned work.

Prefer small, focused modules. Avoid placing generated output, dependency caches, credentials, or editor-specific files under version control.

## Build, Test, and Development Commands

Use `make setup` to install core dependencies and `make setup-radio` when working with the optional official Meshtastic SDK. `make migrate` applies database migrations, while `make run` builds and serves the local application. Run `make dev-backend` and `make dev-frontend` in separate terminals for development. `make demo-two-nodes` verifies the virtual transport; `make transport-info` and `make transport-radio` exercise adapter selection. `make test`, `make lint`, `make typecheck`, and `make build` cover both applications. `make check` runs the complete pre-push suite.

Before submitting work, run every configured formatter, linter, test suite, and build command locally. Commands should be reproducible from the repository root.

Before declaring a feature, bug fix, or substantial change complete, review every applicable item in `CHECKLIST.md` and resolve any unmet item.

For runtime work, use `make desktop` or `make runtime-server`; these use a separate persistent profile from development `make run`. `uv run solora` provides GUI-free status/configuration/server commands after assets are built. Keep the sole app version in `backend/src/solora/version.py`. Do not import `desktop/` or the development ASGI singleton from headless runtime. See `docs/PHASE3A_RUNTIME.md` for ownership, readiness and offline recovery contracts.

## Coding Style & Naming Conventions

Target Python 3.12 and Node.js 24. Ruff controls Python formatting with 4-space indentation and a 100-character line limit; Oxlint and TypeScript check the frontend. Use `snake_case` for Python, `PascalCase` for React components and classes, and `camelCase` for TypeScript functions. Keep domain code independent of frameworks and adapters.

## Testing Guidelines

Add pytest tests with every behavior change or bug fix. Name tests after observable behavior, such as `test_rejects_expired_token`. CI enforces at least 90% coverage. Tests must be deterministic; replace network, clock, filesystem, and radio hardware dependencies with fixtures or fakes.

Create every schema change as an Alembic migration. Never edit an applied migration or rely on automatic table creation; verify upgrades against an existing database so local user data is preserved.

## Commit & Pull Request Guidelines

Use concise Conventional Commit subjects, for example `feat: add radio discovery` or `fix: validate empty device ID`.

Pull requests should explain the problem and solution, list verification performed, and link relevant issues. Include screenshots or logs for visible behavior changes. Keep changes narrowly scoped, call out configuration or compatibility impacts, and never commit secrets; provide sanitized examples such as `.env.example` instead.

## Product and Release Rules

Communicate product-facing summaries in concise Swedish. Keep protocol changes synchronized with `PROTOCOL.md` and milestones with `ROADMAP.md`. Beta versions use `v0.x.x-beta.N`. Never publish or promote a stable release without explicit manual approval from the product owner.

## Meshtastic Sources and Reference Projects

For every radio or transport decision, treat Meshtastic's current official [documentation](https://meshtastic.org/docs/), [protobuf definitions](https://github.com/meshtastic/protobufs), [Python SDK](https://github.com/meshtastic/python), and [firmware](https://github.com/meshtastic/firmware) behavior as authoritative. Check the versions SOLoRa supports; do not rely on remembered constants or old assumptions. If sources disagree, prefer current official protobuf/firmware definitions, then official documentation/SDK behavior, and only then third-party examples. Record the upstream tag or commit behind protocol-critical decisions.

Keep the protocol layers separate:

```text
SOLoRa operations: POST / ACK / SYNC / WANT
SOLoRa compact binary protocol
Meshtastic Data.payload using PortNum = PRIVATE_APP
Meshtastic MeshPacket: routing / ACK / hop limit
LoRa
```

SOLoRa owns only the application protocol inside `Data.payload`. Do not recreate Meshtastic routing, hop handling, transport acknowledgements, or mesh delivery behavior. Before implementation, verify `Data.payload` limits, protobuf overhead, `PortNum`/`PRIVATE_APP`, `MeshPacket`, routing and hop limit, broadcast versus unicast, ACK/routing responses, packet/request IDs, retries, transmit-queue priorities, serial/TCP/BLE behavior, channel utilization, and airtime impact. Current upstream definitions state a 233-byte `Data.payload`, maximum hop limit 7, private port range 256–511, and `PRIVATE_APP = 256`; re-check rather than hard-coding these as timeless facts.

Meshtastic ACK and SOLoRa `COMMIT_ACK` have different meanings. A Meshtastic ACK reports a transport/routing outcome. A `COMMIT_ACK` may be sent only after the receiving SOLoRa authority has received complete content, validated it, and committed it durably. Never infer application persistence from a transport ACK. Never infer authority from the display name `SOL1`; system role must be explicit and protocol-facing authority must use Meshtastic Node ID.

For Meshtastic integration, synchronization, packet handling, node state, persistence, frontend status, and Linux/Raspberry Pi operation, consult these technical references when relevant:

- [TC2-BBS-mesh](https://github.com/TheCommsChannel/TC2-BBS-mesh)
- [Supply Drop BBS](https://github.com/Mesh-America/supply-drop-bbs)
- [MeshMonitor](https://github.com/bordeux/meshmonitor)

Use them only as secondary implementation examples for proven approaches and tradeoffs, never as authorities on Meshtastic behavior. Do not copy their code or architecture wholesale. SOLoRa's architecture and requirements always take precedence, including local-first behavior, persistent forum data, explicit Primary authority with offline-capable clients, low airtime, the compact binary protocol, **Normal state is silent**, user-traffic priority, channel-utilization controls, peer repair, and future backup-server support.

When a reference influences an implementation, briefly document which project was studied, the problem it clarified, and why SOLoRa selected the same or a different approach. Review licensing before reusing any code or other protected material.
