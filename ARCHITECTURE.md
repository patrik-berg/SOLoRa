# Architecture

## Principles

SOLoRa is local-first: core reading and writing must work without internet access. Radio and persistence details stay behind interfaces so automated tests never require physical hardware. The web client and local API are separate build targets with a narrow HTTP boundary.

## Planned components

1. **Web client** — React and TypeScript built by Vite. It owns presentation state only.
2. **API layer** — FastAPI routes that validate input but contain no domain rules.
3. **Application layer** — use cases for threads, posts, synchronization, and node state.
4. **Domain layer** — transport-independent models and invariants.
5. **Persistence adapter** — SQLite through SQLAlchemy, with Alembic migrations.
6. **Transport adapter** — Meshtastic I/O implementing a narrow interface; tests use an in-memory fake.
7. **Updater** — later consumes signed beta metadata and artifacts from GitHub Releases.

Dependencies point inward: web, database, and radio adapters may depend on application interfaces; the domain must not import FastAPI, SQLAlchemy, or Meshtastic.

## Initial data flow

`React client → local FastAPI API → application use case → SQLite`

For node synchronization, an outbox will record committed messages before the Meshtastic adapter transmits them. Received envelopes will be deduplicated before application processing.

## Release policy

GitHub Actions will eventually test and build immutable `v0.x.x-beta.N` artifacts. Beta publication may be automated after the pipeline is proven. Stable versions require an explicit manual approval and must never be published from an ordinary push.
