# Architecture

## Principles

SOLoRa is local-first: reading and writing remain available without internet or radio connectivity. Persistence and transport stay behind application interfaces so CI can exercise all synchronization behavior without hardware. **Normal state is silent**, and queued user content always precedes future background repair traffic.

## Components

1. **Web client** — React/TypeScript built by Vite; presentation state only.
2. **API layer** — FastAPI routes and Pydantic HTTP schemas.
3. **Application layer** — forum use cases plus the hardware-independent `SyncNode` orchestration service.
4. **Domain layer** — forum entities and the compact binary packet codec.
5. **Persistence adapters** — SQLite/SQLAlchemy repositories, versioned by Alembic.
6. **Transport adapters** — a narrow `Transport` interface with deterministic in-memory and USB/serial Meshtastic implementations.
7. **Updater** — future consumer of signed beta artifacts from GitHub Releases.

Dependencies point inward. Domain and application code do not import FastAPI, SQLAlchemy, Meshtastic, serial, TCP, BLE, or generated protobuf types.

## System identity and role

SOLoRa keeps three independent identity concepts:

- `system_name` is user-managed display metadata such as `SOL1` or `Base North`.
- Meshtastic `node_id` is the radio/network identity such as `!91ab22cd`.
- `system_role` is explicit local behavior: `CLIENT`, `PRIMARY`, or `BACKUP`.

`SOL1` is only a conventional name and has no protocol or authority meaning. Primary authority exists only when `system_role = PRIMARY` and is identified externally by Meshtastic Node ID. The domain's authority value intentionally contains no system name, preventing presentation metadata from becoming a routing or trust key.

Name and role are persisted separately in SQLite and may change independently. A role transition requires explicit confirmation through both UI and API. `PRIMARY` and `BACKUP` can be stored for test environments but are currently marked experimental; this setting does not yet activate sequencing, authentication, replication, or failover behavior. A future promotion from Backup to Primary retains the node's actual Node ID and requires no rename.

Future status/discovery may advertise `role`, `node_id`, optional `system_name`, `protocol_version`, `forum_revision`, and a server epoch or equivalent authority generation. Receivers must bind authority to role plus Node ID, never to a display name. This is a planned payload concept only; no v1 message layout or numeric type is changed here. Status should piggyback where possible and preserve **Normal state is silent**.

## Protocol allocation policy

`PROTOCOL.md` is the authoritative SOLoRa message registry. The v1 envelope has a four-bit type field, so its small `0–15` namespace must not be allocated ad hoc in implementation code. Existing numeric meanings are immutable; removed values are not reused. A planned or reserved value becomes implemented only through a focused protocol change that defines its direction, priority, payload layout, size limits, failure behavior, canonical fixture, and compatibility tests. Value 15 remains reserved for future core expansion, with no extension encoding defined yet.

Registry entries describe intent without activating behavior. In particular, reserved status, presence, authentication, fragmentation, and capability types must not be emitted or accepted until their separate designs are approved. New background behavior must preserve **Normal state is silent**, prefer piggybacking, and remain subordinate to user traffic.

## Local application flow

`React client → local FastAPI API → application use case → SQLite`

FastAPI serves the production frontend at `127.0.0.1:8000`. The default database is `data/solora.db`, overridable with `SOLORA_DATABASE_URL`. Alembic migrations must run before startup.

## Phase 2 transport flow

```text
publish POST
→ transaction: local post + encoded outbox item
→ flush due user-priority work
→ Transport.send(destination, bytes, priority)
→ receiver transaction: dedupe ID + persist post
→ COMMIT_ACK
→ sender removes matching outbox item
```

`InMemoryNetwork` connects virtual endpoints, records attempts, can deterministically drop frames, and can replay captured frames. It supplies the same addressing and byte boundary expected from the future Meshtastic adapter while avoiding simulated routing logic. `SqlAlchemySyncRepository` makes application state durable across restarts. Retry scheduling is timestamp-based rather than an in-process sleep, so interruption loses no queued work.

## Hardware-independent repair

Each thread now has a random 96-bit `sync_id`; posts already use 96-bit message IDs. Local SQLite primary keys never cross the transport boundary. An explicit `request_sync(peer)` queues compact inventory pages in the same durable outbox as content. The peer compares object references, persists outstanding repair requests, returns its inventory once, and asks for missing threads/posts with `WANT`. Requested objects are loaded from SQLite and queued as background `THREAD` or `SYNC_POST` frames.

Thread and post persistence remains idempotent by global ID. A post whose thread is unavailable is not marked received and is not acknowledged. Its thread is requested once; after the thread commits, the sender's existing retry delivers the post without special timing. Control messages and content are application-acknowledged, so loss or process restart leaves enough durable state to resume. Inventory and repair traffic uses `BACKGROUND`; user-originated posts and all acknowledgements retain higher priority.

Repair is pull-based and silent until explicitly requested. It currently supports immutable thread titles and posts that fit one radio frame. Fragmentation, conflict rules, automatic sync scheduling, and channel-utilization scheduling remain later Phase 2 work and require physical measurements.

## Meshtastic boundary

`MeshtasticTransport` opens the official Python SDK's `SerialInterface`, publishes bytes through `sendData`, and listens only on `meshtastic.receive.data.PRIVATE_APP`. It maps numeric source/destination fields and raw payload bytes to `InboundFrame`. User traffic maps to Meshtastic `RELIABLE` priority; background work maps to `BACKGROUND`. Unicast asks Meshtastic for a routing ACK, while broadcast deliberately does not. A successful `send()` means the local SDK accepted the packet and returned a non-zero packet ID—not that a peer persisted it. Full local queues, serial exceptions, invalid SDK results, and closed adapters become `TransportError`, leaving the durable outbox responsible for later application retry.

Meshtastic retains responsibility for `MeshPacket` routing, hop limits, packet/request IDs, firmware retries, and routing ACKs. Those ACKs arrive on `ROUTING_APP` and never enter the SOLoRa receiver subscribed to `PRIVATE_APP`. SOLoRa never interprets a routing ACK as durable storage; only the binary v1 `COMMIT_ACK` has that meaning. The adapter contains no retry sleeps or routing implementation.

`TransportSettings` and `create_transport()` select `in-memory`, `meshtastic-serial`, or `meshtastic-network` without changing application/domain code. USB and serial endpoints use the official `SerialInterface`; network endpoints use the official `TCPInterface`. The shared gateway owns the chosen SDK connection for the web-process lifetime and reports local connection loss independently from future mesh/radio reachability. Wiring received frames into a long-running forum-sync service remains deferred until per-callback database-session ownership is specified.

### Local channel binding

Channel discovery is an explicit settings action, never an idle poll. The adapter reads only enabled local channel indices, names, and roles from the official SDK; PSKs and other channel secrets do not cross the infrastructure boundary. The API caches the latest discovery result and SQLite stores only a user-confirmed `(node_id, channel_name, channel_index)` binding. A missing, renamed, moved, or differently connected node invalidates that binding and requires confirmation instead of silently falling back.

The settings flow persists a separate connection profile: `usb` or `serial` plus an opaque cross-platform port identifier, or `network` plus hostname/IP. Serial discovery uses pyserial's platform API and therefore handles Unix device paths and Windows COM ports without path assumptions. Listing devices does not open a node. Only an explicit connection test opens the SDK interface, reads public node name/ID/firmware and channels, records the latest successful contact, and retains the connection. Startup reads cached SQLite status only and never contacts hardware.

Meshtastic channel indices are node-local: two nodes may both use `solora-link` at different indices. Each transport therefore validates its own exact binding. Outbound SOLoRa frames set that index in `sendData`; inbound `PRIVATE_APP` payloads are accepted only when the packet reports the selected local index. Other ports and other channels are ignored. Reading cached status creates no radio packets and the refresh operation only reads local node configuration, preserving **Normal state is silent**.

## Release policy

### Implemented Phase 3A runtime boundary

PR A introduces GUI-free `runtime/` modules for OS paths, atomic bootstrap config,
readiness and process ownership, plus a thin `desktop/window.py` ttk prototype.
The installed-runtime factory lives in `web/application.py`; the development
`app.py` entry is separate so headless startup never creates a development database.
Desktop owns its child through inherited local pipes, while headless is externally
owned. Both lock the same persistent data profile; neither adopts another service.
Frontend assets are served by FastAPI, and `/health/ready` verifies DB/schema/state
and assets independently of radio. Shared configuration is available before HTTP
and read-only in web diagnostics. Application version comes from `version.py`,
not the protocol registry. See [the implemented runtime contract](docs/PHASE3A_RUNTIME.md)
for layout, recovery, test evidence and remaining packaging/platform gates.

The browser's global watchdog consumes `/api/status`, a read-only summary built
from the same readiness checks and cached local radio state. It distinguishes
Online/Degraded/Offline and never drives radio discovery or traffic. Node state is
unknown without a current backend snapshot; Primary heartbeat fields remain null
until actual authority/heartbeat behavior exists. A client-only relative timer
can later age a real heartbeat timestamp without increased HTTP/radio traffic.

### Desktop and headless installation

Distribution is separate from role: **Desktop** targets Windows/macOS; **Server** installs on existing Linux/Raspberry Pi OS on Pi 4/5, preferably via `.deb`; **Appliance** is a flashable, automatically starting headless image for Pi Zero 2 W. Linux desktop controls are optional; Zero 2 W has no desktop, Tkinter, or development tools. All use identical core, protocol, database, sync, roles, transport, and web UI; packaging and OS/recovery adapters provide the differences.

Zero 2 W is the 512 MB minimum performance target for future headless Primary/Backup, never an automatic role assignment. An explicit role choice is required. Primary workload and sustained stability must pass a dedicated physical validation gate before support is claimed. Backup remains non-authoritative while a valid Primary exists; future manual promotion needs authority-generation/fencing rules, not a rename.

Appliance design includes network provisioning and browser first run, independent `solora-config` recovery via local terminal/SSH, service watchdog/restart support, and persistent data separate from OS/application files. Safe rollback must cover database compatibility as well as binaries. Read-only root remains an investigation pending SQLite/logging/update validation. See the delivery design for the full recovery scope and measurement gate.

Phase 3 must include a small local control window as part of the installed desktop app, alongside the existing browser-based forum. A thin shell over a local supervisor displays service readiness, web addresses, interface/port, app version, system name/role, and cached Meshtastic status. It supports Open SOLoRa, Hide/restore, Quit, Start/Restart, applying bind/port changes, Start minimized, and opt-in Run at login. Advanced configuration remains in the web app.

The supervisor owns the desktop backend child and remains usable when HTTP fails. Local process control must be independent of the configurable HTTP listener. Headless mode instead uses an OS service manager and equivalent status/configuration controls, with no GUI dependency. One owner per data profile prevents duplicate services and radio connections. Name, role, and Node ID retain their independent meanings.

The provisional packaging direction is a Python/Tkinter control shell with platform-specific bundles; toolkit selection must pass desktop accessibility, Hide/restore, startup, and platform build gates. Loopback remains the default, wildcard bindings display actual usable addresses, and port/interface changes require explicit Apply with restart/recovery handling. The source-run prototype now implements these controls; installers and login integration remain PR B work. See [Phase 3 desktop delivery design](docs/PHASE3_DESKTOP_DELIVERY.md) for requirements, alternatives, and validation gates.

GitHub Actions will eventually build immutable `v0.x.x-beta.N` artifacts. Stable promotion always requires explicit manual approval.
