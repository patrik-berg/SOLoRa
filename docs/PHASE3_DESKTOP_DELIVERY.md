# Phase 3 — Desktop and Headless Delivery

Status: design requirement, not implemented. SOLoRa must ship as an installable application with a small local control window, as well as an optional headless service. The existing `make run` still starts only the HTTP service. Physical two-radio validation remains an independent, mandatory Phase 2 gate.

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
| Desktop: Windows, macOS, Linux | Desktop supervisor owns one backend child | Small control window; forum and advanced settings in browser | Installed app; optional per-user Run at login |
| Raspberry Pi with desktop | Same desktop model, optional GUI package | Same controls where supported | Desktop login, opt-in |
| Headless/server, including Raspberry Pi | OS service manager owns backend | Service start/stop/restart/status and equivalent local configuration command; browser for forum | Explicit service-at-boot configuration |

Desktop login startup and headless boot startup are different options. Do not register both owners for the same data profile. A control window must not kill or adopt an independently managed server. Report an existing managed service and its ownership instead. Headless mode must not import GUI libraries, require a display, or open a browser. Document service status and the configured web addresses in startup output.

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

PyInstaller builds are OS-specific, so plan separate Windows, macOS, and Linux build jobs and explicit architecture targets. Raspberry Pi ARM64 desktop/headless artifacts require their own build and smoke-test evidence; do not assume a Linux x64 artifact runs on Pi. Start with a one-folder bundle for diagnosability, then wrap it in platform installers. [PyInstaller manual](https://pyinstaller.org/en/stable/)

Desktop artifacts must include the Python runtime, required GUI libraries, backend, migrations, and built frontend so normal users need no developer tools. Headless packages exclude GUI dependencies. Store writable database, logs, and launch preferences outside installed binaries in platform-appropriate application-data locations. Launch preferences (bind, port, minimized, login) are separate from domain identity in SQLite. Upgrades must preserve both, and migrated data needs a recovery plan before rollback. Installer signing, macOS notarization, OS startup adapters, and minimum OS/architecture support must be verified before supported Beta publication.

## Delivery and acceptance gates

1. Prototype the shell/supervisor boundary and measure idle memory, startup time, and artifact size before final toolkit selection.
2. Test lifecycle, single-instance handling, missing interfaces, occupied/invalid ports, failed restart/restore, URL selection, and startup preferences with fakes; require no radio hardware.
3. Smoke-test installed artifacts on Windows, macOS, Linux desktop, and Pi ARM64. Verify keyboard/screen-reader use, Hide/restore, Quit, login opt-in/removal, and retained data after upgrade.
4. Verify headless startup without a display or GUI dependencies, service ownership, logs/status, and configuration repair while HTTP is stopped.
5. Verify cached radio status introduces no additional radio traffic. Keep physical radio validation pending separately.

Beta delivery must package the control window as part of the desktop installation experience. Publish only validated target artifacts and signed update metadata. Stable promotion remains manual. These gates supplement the existing `CHECKLIST.md`, not replace it.
