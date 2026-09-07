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

`TransportSettings` and `create_transport()` select `in-memory` or `meshtastic-serial` through configuration without changing application/domain code. The current diagnostic CLI exercises the adapter directly; wiring a long-running radio service into the web process is deferred until lifecycle and per-callback database-session ownership are specified.

## Release policy

GitHub Actions will eventually build immutable `v0.x.x-beta.N` artifacts. Stable promotion always requires explicit manual approval.
