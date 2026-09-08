# Phase 3A PR A — Checklist evidence

Review against the unchanged root `CHECKLIST.md`:

| Item | Evidence / applicability |
| --- | --- |
| 1–3 Scope, architecture, relevant files | Runtime/desktop adapters, shared web factory/config diagnostics, docs/tests/CI only. Packaging and authority remain out of scope. |
| 4–6 Tests and builds | 114 pytest tests, 19 frontend tests, 93.93% coverage; `make check` includes Ruff, Oxlint, mypy, TypeScript, Python wheel/sdist and Vite build. |
| 7 Documentation | README, ARCHITECTURE, ROADMAP, delivery design and `PHASE3A_RUNTIME.md` updated. |
| 8 Compatibility | Existing developer command and `/health` retained; new readiness endpoint separate. |
| 9 Data safety | No migration files rewritten. Existing migrations run under exclusive profile ownership; tests preserve existing forum data. Development database is not moved or replaced. |
| 10–12 Radio and priority | No wire IDs, payload, sync/retry policy or priority changes. Health/window use only local cached radio state. Virtual-node tests retained. |
| 13 Secrets | No credentials, PSKs or generated local state included. Inspect staged diff before push; subprocess coverage output ignored. |
| 14–15 Git and commit | Separate `codex/phase3a-runtime` branch from verified main; Conventional Commit, scoped PR. |
| 16 CI | Ubuntu full suite plus native Windows/macOS runtime tests passed in [the initial branch run](https://github.com/patrik-berg/SOLoRa/actions/runs/34223828096). Inspect latest PR checks before handoff; no artifact/release publication added. |
| 17 Beta/Stable | Central beta app version; radio version unchanged. Standalone artifacts/release metadata deferred to PR B, no Stable publication. |
| 18 Handoff | Swedish summary with actual tests, coverage, PR/CI status, running preview and outstanding manual gates. |

Real Tk smoke passed on macOS ARM64; this is not a visual accessibility or packaged
Windows certification. Interactive screen/default-browser review was blocked by the
locked Mac. Those checks, native packaged installation/login/icon behavior, Pi 4/5
physical validation and the still-open Phase 2 radio gate are explicitly pending.
No Phase 2/3 completion or installation-without-Python claim is made here.

Browser-watchdog follow-up: scoped read-only status summary and frontend changes;
no schema, wire IDs, radio retry/airtime/priority or release changes. Tests cover
two-failure debounce, timeout/cancellation, degraded versus offline, one dialog per
outage, recovery, draft retention, Node Unknown, honest Primary state and purely
local heartbeat-age updates. Repeated status reads are verified not to invoke
radio discovery or device polling. Full-suite counts and latest CI are recorded
in PR #16 after verification.

The previously blocked browser check is now verified with an isolated server using
the production `ServerController`: the same loaded browser tab changed from Online
to the native offline dialog, then back to Online after restart, closing the dialog
and announcing recovery without navigation/reload. Focus entered the dialog button.
Full Escape/focus-restoration/narrow-screen manual acceptance remains a separate UX
gate; jsdom tests stub native dialog top-layer methods.

## Watchdog prompt audit

| Requested step | Result |
| --- | --- |
| 1. Watchdog | Four-second local status checks, 2.5-second timeout, two network failures before Offline; cancellation and non-overlap tested. |
| 2. Application states | Online/Degraded/Offline are frontend-global and separate from the radio. |
| 3. Dialog/recovery | One native dialog per outage, last-online time, persistent status, automatic close/recovery; browser stop/start verified. |
| 4. Global strip | Sticky Application/Node/Primary strip across views; Node Unknown without a current backend snapshot. |
| 5. Primary heartbeat | Nullable reserved summary fields; actual authority/heartbeat not implemented or fabricated. |
| 6. Relative age | Client-only one-second timestamp display tested without HTTP requests. |
| 7. Errors | Offline hides misleading radio errors; Online still shows genuine radio-request errors. Recovery refreshes cached metadata without resetting drafts. |
| 8. Cached summary | Read-only, no-store `/api/status`; same readiness function, no radio discovery/connection/TX calls. `/health/ready` contract unchanged. |
| 9. Tests/docs/PR | Full local suite green; documentation updated; latest push/CI evidence maintained in PR #16. No merge performed. |
