# Phase 3A PR A — Runtime and desktop proof-of-concept

This change implements the runtime, not an installer or release. Python is still
needed to run the source checkout; **PR B** will bundle it, built frontend assets,
and migrations so normal installed use needs no development tools. No radio
protocol, authority behavior, retry timing, or release-publication rule changes.

## Run from the checkout

After `make setup`, use `make desktop` for the control window or
`make runtime-server` for a foreground, GUI-free production server. These Make
targets build assets first. Thereafter `uv run solora desktop` or
`uv run solora server` starts the runtime without invoking Node/Vite. `make run`
remains the existing development-data workflow on port 8000.

The new runtime deliberately uses a **separate database** from `data/solora.db`.
It never silently relocates, imports, or overwrites the development database.
To carry development data into a runtime profile, stop both owners, back up the
database, then copy it to the profile's data directory before starting runtime.
Never copy an actively written SQLite database without SQLite's backup API.

For an isolated test profile outside the checkout:

```sh
uv run solora --profile /absolute/path/to/solora-profile configure --port 8011 --mode desktop
uv run solora --profile /absolute/path/to/solora-profile desktop
```

On Windows, use a Windows path such as `C:\Users\Patrik\SOLoRa-Test`.
The optional `--application`, `--data`, `--config`, `--logs`, and `--runtime`
arguments let PR B's platform adapter supply service-specific directories.
Writable state inside the application directory is rejected.

## Shared paths and configuration

`RuntimePaths` resolves unversioned paths using `platformdirs`, or explicit
profile/service overrides. Application resources are read-only inputs and contain
`frontend/dist` and `backend/migrations`. The normal user-profile layout is:

| Platform | Database directory | Bootstrap config directory | Logs / transient state |
| --- | --- | --- | --- |
| macOS | `~/Library/Application Support/SOLoRa/data` | `~/Library/Application Support/SOLoRa/config` | `~/Library/Logs/SOLoRa` / `~/Library/Caches/SOLoRa/run` |
| Windows | `%LOCALAPPDATA%\SOLoRa\data` | `%LOCALAPPDATA%\SOLoRa\config` | platformdirs' local log/cache directories |
| Linux user | `$XDG_DATA_HOME/SOLoRa/data` (default `~/.local/share`) | `$XDG_CONFIG_HOME/SOLoRa/config` (default `~/.config`) | XDG state log directory / XDG cache `SOLoRa/run` |

`solora.db` and `runtime.json` are persistent. The latter holds schema version,
IPv4 bind, port, preferred mode, Start minimized, and explicit LAN acknowledgement.
`ConfigStore` validates before atomic same-directory replacement and fsync;
malformed/future config is reported rather than silently reset. Role, identity,
radio endpoint, and channel binding remain in the existing SQLite settings.

Both server and shell use this store. `GET /api/settings/runtime` exposes active
and saved values read-only in web diagnostics. There is intentionally **no LAN
process-control API**. Offline repair uses the same validation:

```sh
uv run solora status
uv run solora configure --bind 127.0.0.1 --port 8011
# Explicit opt-in only, on a trusted network; the forum has no authentication:
uv run solora configure --bind 0.0.0.0 --port 8011 --allow-lan
```

Stop the desktop/service owner before `configure`; exclusive profile locks enforce
this. Restart the owning app or service manager afterwards. `status` prints
configured addresses, not a false assertion of readiness. IPv6 is explicitly not
supported by this first bootstrap schema. Unknown/disappeared interfaces never
fall back automatically. Wildcard binding displays loopback plus local interface
addresses, never `0.0.0.0` as a browser destination; firewall reachability is not assumed.

## Ownership and failure recovery

`ServerController` is widget-independent. Desktop holds a profile owner lock and
starts one child with inherited private stdin/stdout pipes. Closing stdin requests
graceful shutdown; parent death also closes it. Uvicorn finishes in-flight requests
within a bounded grace period and closes database/radio resources. Only this
controller's own `Popen` child may be terminated/killed if graceful shutdown hangs.

The server holds a second OS-backed file lock in the data directory. A headless
service cannot start over a desktop owner or another service. Locks are released
by the OS on death; lock files are not unlinked or trusted as PID-only ownership.
A second desktop launch sends a same-user restore-file notification to the first
window, not a process-control command or a second radio connection.

The child pre-binds the actual listener before migrations, avoiding a misleading
health response from another application already using that port. It emits local
readiness/status snapshots through its inherited pipe. These read cached radio
status only; **no radio polling or additional mesh packets** are introduced.
Missing/stale status disables Open SOLoRa. Control/configuration remains available
even with broken HTTP. Headless owns its process directly under a future service
manager and never imports Tkinter or opens a browser.

Apply validates, stops the child, saves desired configuration, and attempts start.
On failed start it restores the previous configuration and attempts it again;
the error remains visible even if restoration succeeds. Failure of restoration
leaves an editable error state. Active values are distinct from saved values.
The rotating server log has three 2 MB backups; startup diagnostics are replaced
each launch. No firewall, login item, or system service is installed in PR A.

## Production readiness and version

`GET /health/ready` is contract version 1. HTTP 200 / `status: healthy` requires:

- Backend responsive, database readable, Alembic revision equal to bundled heads.
- System identity and radio configuration readable through existing repositories.
- Production `index.html` and its local script/style/module-preload references present.

Otherwise it returns HTTP 503 with named boolean checks. No raw database errors,
paths, or radio secrets appear in this public health response. Radio can be
Offline while application health is Healthy. Existing `/health` remains a simple
liveness endpoint and **must not be used by a future updater as readiness**.
The shell uses the same readiness function after Uvicorn starts its bound socket.

`solora/version.py` is the single application-version source for Hatch metadata,
API/diagnostics, CLI, and shell. Python normalizes `0.2.0-beta.1` to `0.2.0b1` in
package metadata; these are the same version. The private frontend package no
longer carries a competing release version. Protocol version remains 1.

## Toolkit result and remaining gates

The implementation uses `tkinter.ttk`, with lifecycle operations on a worker and
widgets on the main Tk thread. Hide/close uses the documented native minimized
window fallback (Dock/taskbar); reopening restores it. No custom tray framework
or Electron runtime is introduced. Start minimized is applied only after healthy
startup. Run at login is visibly deferred to packaged OS integration in PR B.

On macOS ARM64, Python 3.12.14 / Tk 9.0.4, the real-window automated smoke on
2026-09-08 passed launch, native minimize/restore, available keyboard focus chain,
invalid/occupied-port handling, successful port change, restart/stop and clean Quit.
One source-run sample: **1.04 s** to healthy; **120.8 MiB** desktop RSS and
**80.7 MiB** child RSS. These are observations, not performance budgets or packaged
measurements. Browser URL selection is tested; the automated smoke mocks activation.
Interactive visual/screen-reader/default-browser checks were blocked by a locked Mac.

Tkinter remains **provisional**, not permanently selected. PR B must test native
Windows/macOS bundles, icon/login integration, browser activation, focus/assistive
technology, startup/memory and persistence without Python installed. If native
minimize/restore or accessibility is inadequate, Tauri with the same child/runtime
boundary remains the concrete alternative; it adds Rust/sidecar packaging but
does not require rewriting forum or process logic.

Sources: [official Tkinter documentation](https://docs.python.org/3.12/library/tkinter.html),
[platformdirs API](https://platformdirs.readthedocs.io/en/latest/api.html),
[psutil](https://psutil.io/), and the existing delivery design's Tauri/PyInstaller references.

## Verification and PR B boundary

`make check` covers all existing forum/virtual-node tests plus real subprocess
startup, restart, graceful/abrupt-parent shutdown, ownership, port conflict,
config recovery, assets, health, version separation and database preservation.
Coverage includes child processes. Ttk wiring uses fakes in CI; opt-in
`uv run python tests/desktop_smoke.py` exercises real Tk on a desktop. CI also
runs runtime tests natively on Windows 2022 and macOS ARM64, without a display/radio.

PR B owns standalone desktop bundles, icons, opt-in OS login registration,
Linux/ARM64 `.deb`/service permissions, artifact build CI and metadata, and any
explicit prerelease publication workflow. No ordinary push publishes Stable.
No standalone installation or physical Pi 4/5 support is claimed by PR A.
Zero 2 W image, Primary/Backup runtime, signing, updater/rollback and new wire IDs
remain out of scope. Physical two-radio and Zero 2 W performance gates remain open.

| Target | PR A evidence | Still required |
| --- | --- | --- |
| macOS ARM | Source runtime + real Tk scripted lifecycle | Interactive UX, default browser, packaged app/login/icon |
| Windows x64 | Native runtime CI configured | Green native CI, real window and packaged lifecycle/login |
| macOS Intel | Shared portable code only | Native build and full desktop matrix in PR B |
| Linux x64 | Headless/runtime integration CI | Installed service/reboot/upgrade in PR B |
| Pi 4/5 | Shared GUI-free runtime architecture | Native package, physical install/reboot/LAN/USB/persistence |
| Zero 2 W | No headless GUI imports; no image | Later boot/RAM/CPU/SQLite/web/sync/authority/stability gate |
