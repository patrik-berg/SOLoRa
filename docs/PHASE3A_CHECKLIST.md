# Phase 3A PR A — Checklist evidence

Review against the unchanged root `CHECKLIST.md`:

| Item | Evidence / applicability |
| --- | --- |
| 1–3 Scope, architecture, relevant files | Runtime/desktop adapters, shared web factory/config diagnostics, docs/tests/CI only. Packaging and authority remain out of scope. |
| 4–6 Tests and builds | 112 pytest tests, 8 frontend tests, 93.81% coverage; `make check` includes Ruff, Oxlint, mypy, TypeScript, Python wheel/sdist and Vite build. |
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
