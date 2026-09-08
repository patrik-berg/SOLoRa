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

### Phase 3A PR A — runtime foundation

- [x] Serve built React assets through the production FastAPI factory without Node at runtime.
- [x] Separate persistent paths from application files; share atomic bootstrap config before HTTP startup.
- [x] Centralize application version independently from the unchanged radio protocol.
- [x] Add `/health/ready` for database, migrations, state and production assets; radio is optional.
- [x] Implement exclusive desktop/server ownership, private-pipe status/shutdown and failed-start recovery.
- [x] Add ttk control-window proof-of-concept with Apply, Open, Restart, Stop, native minimize/restore, Quit and Start minimized.
- [x] Exercise real child-process lifecycle and GUI-free startup automatically; real macOS Tk scripted smoke passes.
- [ ] Complete interactive desktop accessibility/browser checks and native packaged toolkit validation.
- [ ] **PR B:** standalone artifacts, OS login/icon integration, Linux/Pi service packages, build CI and release metadata.

PR A is not an installer or completed Phase 3. See [runtime evidence and remaining gates](docs/PHASE3A_RUNTIME.md).

### Overall delivery gates

- [x] Document the [desktop control window and headless delivery design](docs/PHASE3_DESKTOP_DELIVERY.md).
- [x] Define Desktop (Windows/macOS), Server (Linux/Pi 4/5 on existing OS), and Appliance (Zero 2 W SD image) as distribution models independent of role.
- [ ] Package Server for existing Raspberry Pi OS on Pi 4/5, preferably `.deb`, without requiring a dedicated image.
- [ ] Produce a minimal Zero 2 W Appliance image: flash → boot → automatic service, no GUI/development tools, shared SOLoRa core.
- [ ] Implement secure network provisioning, advertised URL/IP fallback, and explicit identity/radio/channel first-run wizard.
- [ ] Provide `solora-config` for offline-capable identity, radio/channel, bind/port, network, diagnostics, restart, and service recovery with manual device override.
- [ ] Validate persistent data separation, watchdog/restart, power-loss recovery, backup/restore, and safe application/database rollback; investigate read-only root only afterwards.
- [ ] **Required Zero 2 W Primary/Backup gate:** physically measure idle RAM/CPU, startup, SQLite/web latency, sync bursts, reconnect/repair, auth, replication, temperature and sustained stability within the 512 MB target. Unimplemented auth/replication measurements remain pending.
- [ ] Validate a thin control-window toolkit and platform packaging prototype (provisionally Python/Tkinter + PyInstaller).
- [x] Implement prototype desktop status, usable URLs, interface/port Apply, Open, Hide/restore, Quit, and Start/Restart.
- [ ] Persist Start minimized and opt-in Run at login, with platform-specific startup adapters.
- [x] Provide independent supervisor controls so HTTP bind failures can be repaired from the window.
- [x] Provide GUI-free headless runtime and offline bootstrap status/configuration controls; Raspberry Pi packaging remains unverified.
- [ ] Produce and smoke-test platform/architecture-specific installable artifacts, preserving user data outside binaries.
- [ ] Automate versioning as `v0.x.x-beta.N`.
- [ ] Publish prereleases through GitHub Actions.
- [ ] Add signed update metadata and an opt-in **Install beta** flow.

## Stable releases

Stable promotion is always manual. It requires an approved release checklist, successful CI, migration verification, and explicit product-owner approval.
