# Roadmap

## Phase 0 — Development foundation

- [x] Initialize Git and connect GitHub.
- [x] Document architecture, protocol boundaries, and contribution rules.
- [x] Add a minimal local server scaffold and automated tests.
- [x] Add a minimal React/Vite frontend scaffold and automated tests.
- [x] Run lint, type checks, tests, and build validation in GitHub Actions.
- [ ] Add branch protection after CI is stable.

## Phase 1 — Local MVP

- **Status: complete.** Final browser, persistence, accessibility, responsive-layout, and CI quality pass completed.
- [x] Add SQLite migrations and repositories.
- [x] Create, list, and display local forum threads and posts.
- [x] Connect the React interface to the local API.
- [x] Prove restart persistence and migration behavior in automated tests.
- [x] Perform browser-based accessibility and usability testing before Phase 2.

## Phase 2 — Two-node transport

- **Status: serial adapter and hardware-independent repair implemented; physical two-radio validation remains.**
- [x] Define a compact, versioned single-frame packet envelope.
- [x] Add 96-bit message IDs, transactional deduplication, and `COMMIT_ACK` semantics.
- [x] Persist an offline outbox with user-first priority and bounded exponential retry.
- [x] Simulate loss, resend, duplicate delivery, acknowledgement, and restart with two virtual nodes.
- [x] Add a thin USB/serial adapter using the official Meshtastic Python SDK and `PRIVATE_APP`.
- [x] Cover serial mapping, routing-ACK isolation, queue errors, and selection with hardware-free mocks.
- [x] Discover enabled node channels and persist an exact, user-confirmed node/name/index binding.
- [x] Restrict `PRIVATE_APP` transmit and receive to the selected local channel without exposing PSKs.
- [x] Add persisted, web-managed USB/serial/network configuration and cross-platform device discovery.
- [x] Show local node identity, firmware, latest contact, connection loss, and a home-page status link.
- [x] Persist an explicit system name and `CLIENT`/`PRIMARY`/`BACKUP` role independently.
- [x] Add role-change confirmation, header identity, and browser-visible diagnostics.
- [x] Define future authority identity as explicit role plus Meshtastic Node ID, never `SOL1`.
- [x] Add explicit `SYNC` inventories, batched `WANT`, missing-thread repair, and idempotent object transfer.
- [x] Prove offline → reconnect → packet loss → bidirectional convergence with virtual nodes.
- [ ] **Required Phase 2 validation gate:** execute the documented end-to-end procedure with two physical Meshtastic nodes.
- [ ] Measure real payload overhead, airtime, queue behavior, ACKs, and channel utilization.
- [ ] Decide fragmentation and automatic scheduling only after physical-radio measurements.
- [ ] Implement Primary/Backup sequencing, replication, discovery, and failover semantics; stored server roles remain experimental until then.

## Phase 3 — Beta delivery

- [x] Document the [desktop control window and headless delivery design](docs/PHASE3_DESKTOP_DELIVERY.md).
- [ ] Validate a thin control-window toolkit and platform packaging prototype (provisionally Python/Tkinter + PyInstaller).
- [ ] Implement desktop status, usable URLs, interface/port Apply, Open, Hide/restore, Quit, and Start/Restart.
- [ ] Persist Start minimized and opt-in Run at login, with platform-specific startup adapters.
- [ ] Provide independent supervisor controls so HTTP bind failures can be repaired from the window.
- [ ] Provide GUI-free headless/service mode, including Raspberry Pi status and configuration controls.
- [ ] Produce and smoke-test platform/architecture-specific installable artifacts, preserving user data outside binaries.
- [ ] Automate versioning as `v0.x.x-beta.N`.
- [ ] Publish prereleases through GitHub Actions.
- [ ] Add signed update metadata and an opt-in **Install beta** flow.

## Stable releases

Stable promotion is always manual. It requires an approved release checklist, successful CI, migration verification, and explicit product-owner approval.
