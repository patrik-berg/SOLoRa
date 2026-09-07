# Architecture

## Principles

SOLoRa is local-first: core reading and writing must work without internet access. Radio and persistence details stay behind interfaces so automated tests never require physical hardware. The web client and local API are separate build targets with a narrow HTTP boundary.

## Components

1. **Web client** — React and TypeScript built by Vite. It owns presentation state only.
2. **API layer** — FastAPI routes and Pydantic request/response schemas.
3. **Application layer** — framework-independent thread and post use cases and validation.
4. **Domain layer** — transport-independent models and invariants.
5. **Persistence adapter** — SQLite through SQLAlchemy, versioned by Alembic migrations.
6. **Transport adapter** — planned Meshtastic I/O behind a narrow interface; not implemented in Phase 1.
7. **Updater** — later consumes signed beta metadata and artifacts from GitHub Releases.

Dependencies point inward: web, database, and radio adapters may depend on application interfaces; the domain must not import FastAPI, SQLAlchemy, or Meshtastic.

## Initial data flow

`React client → local FastAPI API → application use case → SQLite`

The production Vite build is served by FastAPI at `127.0.0.1:8000`. During development, Vite proxies `/api` and `/health` to FastAPI. The default database is `data/solora.db`; `SOLORA_DATABASE_URL` can override it for tests or controlled deployments. Migrations must run before the server starts and are never replaced with implicit table creation.

For later node synchronization, an outbox will record committed messages before the Meshtastic adapter transmits them. Received envelopes will be deduplicated before application processing.

## Release policy

GitHub Actions will eventually test and build immutable `v0.x.x-beta.N` artifacts. Beta publication may be automated after the pipeline is proven. Stable versions require an explicit manual approval and must never be published from an ordinary push.
