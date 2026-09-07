# Roadmap

## Phase 0 — Development foundation

- [x] Initialize Git and connect GitHub.
- [x] Document architecture, protocol boundaries, and contribution rules.
- [x] Add a minimal local server scaffold and automated tests.
- [x] Add a minimal React/Vite frontend scaffold and automated tests.
- [x] Run lint, type checks, tests, and build validation in GitHub Actions.
- [ ] Add branch protection after CI is stable.

## Phase 1 — Local MVP

- Add SQLite migrations and repositories.
- Create and display one forum thread with posts.
- Connect the accessible React interface to the local API.
- Prove backup and migration behavior.

## Phase 2 — Two-node transport

- Define the first measured wire format.
- Connect two Meshtastic nodes through an adapter.
- Add deduplication, retry, offline outbox, and hardware-free integration tests.

## Phase 3 — Beta delivery

- Produce cross-platform build artifacts.
- Automate versioning as `v0.x.x-beta.N`.
- Publish prereleases through GitHub Actions.
- Add signed update metadata and an opt-in **Install beta** flow.

## Stable releases

Stable promotion is always manual. It requires an approved release checklist, successful CI, migration verification, and explicit product-owner approval.
