# Phase 3 — Desktop, Server, and Appliance Delivery

Status: requirements with an implemented Phase 3A PR A runtime/control-window prototype. See [actual implementation and validation](PHASE3A_RUNTIME.md); packaging, login integration and platform acceptance are still pending. SOLoRa has three distribution models: Desktop, Server, and Appliance. These are packaging choices, never system roles. The existing `make run` still starts only the development HTTP service. Physical two-radio validation remains an independent, mandatory Phase 2 gate.

## User experience

The Companion-style inspiration is operational: launch the installed app, see service status, and open the forum in the default browser. The control window is not another forum client. Advanced settings, including radio configuration and confirmed role changes, remain in the web app.

The window must show:

- SOLoRa application version and service state: starting, running, stopped, or error.
- Current usable web URL(s), selected interface/bind address, and HTTP port.
- Persisted system name and explicit system role, retaining experimental server-role labels.
- Local Meshtastic connection status, such as Online via USB, Online via Network, or Offline; this does not assert mesh reachability.

Provide Open SOLoRa / Launch GUI, Hide, Quit, Start/Restart service, and explicit Apply controls for interface and port. Open is enabled only after service readiness is confirmed. URLs must be copyable. Start minimized and Run at login are persistent, independently configurable toggles, both off by default. First run and startup errors should remain visible until acknowledged.

Hide keeps the service running. Closing the window has the same behavior, with an initial explanation. A tray/menu-bar action or reopening the installed application must restore the existing window. If a desktop lacks reliable tray support, use an accessible minimized-window fallback; never leave the user with an unreachable hidden process. Quit stops the desktop-owned service gracefully before exiting. A second launch raises the existing window instead of starting another service.

## Deployment modes and ownership

| Mode | Process owner | Local controls | Startup |
| --- | --- | --- | --- |
| SOLoRa Desktop: Windows, macOS | Desktop supervisor owns one backend child | Small control window; forum and advanced settings in browser | Installed app; optional per-user Run at login |
| SOLoRa Server: Linux, Raspberry Pi 4/5 with existing Raspberry Pi OS | OS service manager owns backend | Web UI plus local service/configuration tools; prefer a ready-made `.deb` on Debian-based systems | Package installation with documented service-at-boot setup |
| SOLoRa Appliance: Raspberry Pi Zero 2 W | Image-provided service manager owns backend | Headless web UI and `solora-config`; no desktop or Tkinter | Flash SD image → boot → service starts automatically |

Pi 4/5 normally run SOLoRa alongside other software on their existing OS; a dedicated image is not required. An optional appliance image for them may be considered later. Linux desktop controls remain an optional extension where a desktop exists, with explicit ownership selection; installing the Server package must not require a GUI. Zero 2 W never includes the control window.

Desktop login startup and headless boot startup are different options. Do not register both owners for the same data profile. A control window must not kill or adopt an independently managed server. Report an existing managed service and its ownership instead. Headless mode must not import GUI libraries, require a display, or open a browser. Document service status and the configured web addresses in startup output.

## Raspberry Pi Zero 2 W Appliance

The appliance is a dedicated SOLoRa device: flash a prepared SD-card image and boot, without manually installing or administering a general-purpose desktop OS. A minimal Linux/Raspberry Pi OS base is acceptable. Runtime images contain no desktop, Tkinter, or development tools; Python runtime, built web assets, migrations, and recovery tools remain available. Design for the 512 MB RAM budget, low idle overhead, bounded logs, persistent database/config, and unattended 24/7 operation.

All distributions use the same backend/core, protocol, database model, sync engine, system roles, Meshtastic transport, and web UI. Differences belong only in packaging, startup/service ownership, OS integration, and recovery/configuration tooling. Build tooling stays in CI, not in the image. Do not fork an appliance-specific application core.

Primary and Backup are intended appliance use cases, but hardware must never choose the role. First run requires an explicit `CLIENT`, `PRIMARY`, or `BACKUP` choice; an unconfigured appliance must not act as an authority. System name remains display metadata, Node ID remains network identity, and roles remain independent of both hardware and naming.

Design the shared core so Zero 2 W can eventually host the authoritative forum archive, final durable commit and sequence/order, accounts/auth, pending posts, sync/repair, presence/status, and backup replication. This is a performance target, not verified support or an implementation claim.

A future Backup stores complete replicated state, displays replication status, and resumes after reboot. It can be manually promoted to Primary without renaming. While a valid Primary exists, a Backup must not assign final sequence values or act as authority. A role setting alone is not a safe promotion protocol: future promotion needs validated authority-generation/fencing rules to prevent split-brain, including when an old Primary reconnects.

### First run and network access

Target flow: flash image → boot → automatic service startup → network available → open the advertised local address → wizard for system name, explicit role, USB/Serial/Network connection, device/host, and confirmed channel → ready. The service must tolerate a delayed network or unavailable radio without crash loops or lost configuration.

Network provisioning must be designed before image release: provide an image-flashing/first-boot provisioning path that does not require interactive OS administration. Credentials must be device-specific, never baked into a public image. `http://solora.local` is a desired discovery experience, conditional on hostname resolution and a configured port-80 listener/proxy; with the current port use `http://solora.local:8000/`. Show an actual IP/port fallback, handle hostname collisions, and do not assume mDNS is available on every LAN.

Unlike Desktop's loopback default, an appliance needs deliberately provisioned LAN access. The image/setup flow must explain that exposure. Before distributing a network-accessible image, define restricted first-run setup access and protect local management; the current unauthenticated forum must not silently become an unrestricted appliance setup API. SSH recovery requires explicitly provisioned secure access, with no shared default password.

### Recovery and configuration

Provide a planned terminal tool, `solora-config`, usable through SSH or local terminal even when HTTP cannot start. It must offer:

1. System name and explicit, confirmed system role.
2. Meshtastic USB/Serial/Network selection, device discovery with manual path override (including `/dev/ttyACM0` and `/dev/ttyUSB0`), and network host.
3. Enabled channel discovery and explicit local node/channel-index binding; no automatic fallback if missing.
4. Web bind address and port, network settings/status, diagnostics, service status, and restart.

Reuse shared configuration validation and role/channel confirmation rules. When the service is running, use owner-restricted management IPC. Offline repair must acquire exclusive ownership before changing persisted settings, avoiding concurrent database writes or a second radio connection. Device discovery may fail; manual endpoint input must always remain available. Offline channel input is pending validation, not permission to transmit on an unverified channel. Never print PSKs or stored network secrets in diagnostics.

### Persistence and recovery

Separate replaceable OS/application files from persistent SOLoRa database and config. Use graceful service shutdown, bounded restart backoff, and watchdog-compatible readiness/liveness reporting. A watchdog must detect a stuck local process, not treat radio silence as failure. Do not use health checks to generate mesh traffic.

Plan power-loss recovery tests, backups/restores, and a future A/B image update or equivalent safe rollback. OS rollback alone is insufficient after a schema migration: preserve a compatible database recovery path. Avoid unnecessary flash writes and unbounded logging, without weakening durable commit guarantees. Investigate read-only/partially read-only root only after verifying SQLite journals, logging, provisioning, and update requirements; it is not selected or implemented here.

### Mandatory Zero 2 W Primary validation gate

Zero 2 W is the lowest performance target for headless Primary/Backup. Do not mark it officially verified until physical tests record idle RAM/CPU, startup time, SQLite latency, web response time, sync bursts, reconnect/repair load, auth load, backup replication load, and temperature/stability during sustained operation. Record OS/architecture, software version, database size, workload, power supply, and storage media. Define pass/fail budgets before measurement rather than inventing successful limits now. Auth/replication measurements stay pending until those features exist. Include reboot, power-loss, watchdog restart, and upgrade/restore tests. This gate is separate from two-radio transport validation.

## Thin shell and lifecycle boundary

Use a small presentation adapter over a testable local supervisor, which starts the existing backend with the built React assets. Domain/application code remains GUI-independent. Proposed modules are `desktop/` for window presentation and `runtime/` for supervisor, launch configuration, status snapshots, and platform startup adapters; these are planned paths, not existing modules.

The supervisor remains alive when the HTTP child fails. Bind/port configuration must be readable and editable without HTTP. Use owner-restricted local IPC for child readiness, cached system/radio status, graceful stop, and errors, independent of the forum listener. Do not expose process-control commands on the LAN HTTP API. The child remains the owner of SQLite and Meshtastic connections; the window must not open a second radio connection or implement sync.

Display last-known metadata as stale when the service stops. Consume local status events or explicit refreshes; no radio polls, presence packets, or beacons are introduced. **Normal state is silent** and user/background traffic priorities remain unchanged.

## Network interface and port

Default to loopback `127.0.0.1:8000`. Offer localhost, all interfaces, and discovered local addresses with readable interface labels. Persist the explicit address, not an unstable list position. Do not silently switch interface or port when one disappears or is occupied.

| Binding | Display and browser target |
| --- | --- |
| `127.0.0.1:8000` | Local only — `http://127.0.0.1:8000/` |
| `0.0.0.0:8000` | All IPv4 interfaces — list loopback and current eligible LAN URLs separately |
| `192.168.1.42:8000` | Selected LAN address — `http://192.168.1.42:8000/` |

Wildcard addresses are bind instructions, never browser URLs. With multiple adapters, show the available addresses without guessing which one another device can reach. Label LAN links as local-interface addresses: firewall/routing reachability is not verified. Future IPv6 support must use bracketed URLs and explicitly define dual-stack behavior.

Validate a concrete local IP and integer port 1–65535, including permission errors for privileged ports. Apply clearly indicates that a service restart will disconnect browser sessions. Keep desired and active values distinct; validate, shut down gracefully, attempt the new bind, and persist the successful configuration. On failure, report the error and attempt the previous configuration; if restoration also fails, leave the control window usable in stopped/error state. Do not terminate another process occupying the port.

LAN exposure requires explicit acknowledgement that the current forum has no authentication. Never enable LAN access, alter a firewall, or configure port forwarding silently. Desktop management remains local regardless of web binding.

## Toolkit and packaging decision

Provisional recommendation: `tkinter.ttk` for the small Python control window, with PyInstaller as the first packaging candidate. Tk supports Windows, macOS, and Unix; themed widgets fit this small form/status UI. This reuses the current language and leaves the main React forum in the browser. Tcl/Tk availability, accessibility, tray integration, and startup registration still require platform validation; Tk alone is not a complete installer or tray solution. [Python 3.12 Tkinter documentation](https://docs.python.org/3.12/library/tkinter.html)

Tauri is an alternative if the prototype cannot meet those UX gates. Its external-binary/sidecar model can wrap a bundled Python backend, but adds another build toolchain and shell integration surface. No toolkit is added in this documentation task. [Tauri sidecar documentation](https://v2.tauri.app/develop/sidecar/)

PyInstaller builds are OS-specific, so plan separate build jobs and explicit architecture targets. Start with a one-folder desktop bundle for diagnosability, then wrap it in platform installers. This is not a requirement to use PyInstaller for Server `.deb` packages or Appliance images. [PyInstaller manual](https://pyinstaller.org/en/stable/)

For Pi, validate the selected OS/architecture and dependencies on actual hardware; do not assume a Linux x64 artifact runs on Pi. Choose the Zero 2 W image architecture from compatibility and memory measurements, not an untested ARM64-only assumption. Reuse the same versioned core and frontend build in Server packages and reproducible Appliance images; add only the distribution's runtime dependencies, service integration, and recovery tools.

Desktop artifacts must include the Python runtime, required GUI libraries, backend, migrations, and built frontend so normal users need no developer tools. Headless packages exclude GUI dependencies. Store writable database, logs, and launch preferences outside installed binaries in platform-appropriate application-data locations. Launch preferences (bind, port, minimized, login) are separate from domain identity in SQLite. Upgrades must preserve both, and migrated data needs a recovery plan before rollback. Installer signing, macOS notarization, OS startup adapters, and minimum OS/architecture support must be verified before supported Beta publication.

## Delivery and acceptance gates

1. Prototype the shell/supervisor boundary and measure idle memory, startup time, and artifact size before final toolkit selection.
2. Test lifecycle, single-instance handling, missing interfaces, occupied/invalid ports, failed restart/restore, URL selection, and startup preferences with fakes; require no radio hardware.
3. Smoke-test Desktop artifacts on Windows/macOS and any optional Linux desktop target. Verify keyboard/screen-reader use, Hide/restore, Quit, login opt-in/removal, and retained data after upgrade. Separately test Server packages on Linux/Pi 4/5 and flash/boot/recovery on Zero 2 W Appliance.
4. Verify headless startup without a display or GUI dependencies, service ownership, logs/status, and configuration repair while HTTP is stopped.
5. Verify cached radio status introduces no additional radio traffic. Keep physical radio validation pending separately.
6. Complete the Zero 2 W Primary performance/robustness gate before claiming verified Primary/Backup appliance support.

Beta delivery must package the control window as part of the desktop installation experience. Publish only validated target artifacts and signed update metadata. Stable promotion remains manual. These gates supplement the existing `CHECKLIST.md`, not replace it.
