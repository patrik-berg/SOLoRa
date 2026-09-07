# Architecture

## Principles

SOLoRa is local-first: reading and writing remain available without internet or radio connectivity. Persistence and transport stay behind application interfaces so CI can exercise all synchronization behavior without hardware. **Normal state is silent**, and queued user content always precedes future background repair traffic.

## Components

1. **Web client** — React/TypeScript built by Vite; presentation state only.
2. **API layer** — FastAPI routes and Pydantic HTTP schemas.
3. **Application layer** — forum use cases plus the hardware-independent `SyncNode` orchestration service.
4. **Domain layer** — forum entities and the compact binary packet codec.
5. **Persistence adapters** — SQLite/SQLAlchemy repositories, versioned by Alembic.
6. **Transport adapters** — a narrow `Transport` interface; deterministic in-memory implementation now, Meshtastic later.
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

This foundation only transfers a post to a thread already known by both nodes. Missing-thread negotiation, `WANT`/`SYNC`, fragmentation, conflict rules, channel-utilization scheduling, and hardware connectivity remain later Phase 2 tasks.

## Meshtastic boundary

The future adapter maps SOLoRa frames to official `Data.payload`, initially with `PRIVATE_APP`, and maps official source/destination and queue results back to the transport interface. Meshtastic retains responsibility for `MeshPacket` routing, hop limits, packet/request IDs, and transport ACKs. SOLoRa never interprets a routing ACK as durable storage; only `COMMIT_ACK` has that meaning.

## Release policy

GitHub Actions will eventually build immutable `v0.x.x-beta.N` artifacts. Stable promotion always requires explicit manual approval.
