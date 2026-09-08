# Traffic Log — prompt and checklist audit

Scope: passive diagnostics only, based on main `f3048d4` after PR #16 merged with
green main CI. Work branch: `codex/phase3a-traffic-log`. Do not auto-merge this PR.

## Prompt coverage

| Prompt | Implementation / evidence |
| --- | --- |
| 1–2: page, layout | Trafiklogg navigation; dark panels, desktop sidebar/details, toolbar and table. |
| 3–5: capture, passivity, model | Optional TrafficSink; immutable observation/event; Meshtastic sendData boundary and RX after channel/port filtering. Failure isolation tested. |
| 6: buffer | 1000 bounded volatile events, oldest eviction; no per-packet DB writes. Nonblocking capture may discard diagnostics under contention. |
| 7: live stream | Local SSE initial snapshot/deltas/keepalive, reconnect, revision/session cursors; no radio poll. |
| 8: pause | Freezes presentation only; latest bounded snapshot continues receiving. Resume displays retained frames. |
| 9: clear | Explicit confirmation; only TrafficBuffer cleared. Populated outbox/dedupe/forum remain intact. |
| 10: filters | Direction, implemented MessageType registry and node/ID/channel/text search; no network operations for filters. |
| 11–12: details | Metadata, human decoded text, structured envelope/payload parsing, exact HEX offsets/ASCII and copy. |
| 13: malformed | Public malformed v1 retains HEX and generic error; unknown versions/types hidden safely. |
| 14: ACK | SDK Sent versus application COMMIT_ACK explicitly distinguished. ROUTING_APP excluded; no routing-ACK state invented. |
| 15: channel | Actual local name/index retained per event; channel changes preserve old metadata and detach old observer. |
| 16: export | Whole current backend buffer to JSON with versions, UTC time, identity and allowed raw data. |
| 17: secrets | No SDK/config dictionaries or PSKs; explicit v1 type allowlist. New/unknown/AUTH payloads and IDs hidden before retention. |
| 18: performance | Bounded memory/frames, no persistent packet history, no subscriber queues, parser outside capture lock. |
| 19: responsive | Real Chromium 1600px desktop and 390px mobile; stacked cards, keyboard row activation, scrollable HEX. |
| 20: status | Existing global watchdog stays authoritative; real browser offline/recovery retains rows, auto-reconnects without reload. |
| 21: log scope | Radio Traffic Log explicitly separate from deferred Application/System Log. |
| 22: tests | pytest buffer/codec/privacy/adapter/gateway/virtual/SSE/state-isolation + Vitest UI/filter/pause/recovery/export contracts. |
| 23: physical preparation | MESHTASTIC_HARDWARE_TEST.md has TX/RX/HEX/IDs/channel/COMMIT_ACK/retry/export comparison steps and explicit runtime prerequisites. |
| 24: docs | README, ARCHITECTURE, PROTOCOL, ROADMAP and diagnostic/hardware guides updated. |
| 25: exclusions | No wire changes, auth, fragmentation, Primary heartbeat, replay/injection/send endpoint, permanent packet DB or full app log. |
| 26: end-to-end | Real browser validates virtual adapter TX/RX and detail views; mock SDK verifies actual transport mappings. Physical RF evidence remains pending. |

## Existing runtime boundary (not hidden by diagnostics)

The web Settings gateway already owns a live connection and now observes its
confirmed-channel RX. Transport callers can share the runtime buffer for TX/RX.
Local forum HTTP writes still do not run continuous SyncNode work. Separate CLI
processes do not share memory. This feature does not claim that the deferred forum
sync lifecycle or the physical forum-button gate is complete. No production test
injection endpoint was added to create artificial log entries.

## CHECKLIST.md

1–3: Scope follows transport/application/web separation; no unrelated behavior.
4–6: Full make check includes backend/frontend, Ruff/Oxlint, mypy/TypeScript and
Python/Vite production builds. Final counts and CI evidence are recorded in the PR.
7–8: Docs updated; optional sinks preserve default callers and wire compatibility.
9: No migration/schema change. Clear isolation tested with persistent state populated.
10–12: No new LoRa packets, polling, priorities, retries or airtime policy. Passive
operations tested with fake SDK and virtual network counts.
13: Secrets excluded before retention; current public forum text is intentionally
visible and exports must be handled as private. No credentials committed.
14–15: Only intended files staged; Conventional Commit and clean status checked at handoff.
16–17: Existing CI reused, no release workflow changes or automatic Stable publication.
18: Swedish handoff includes tests, PR/CI, preview address and remaining physical gate.

## Browser evidence

Final local `make check`: **138 backend tests, 29 frontend tests, 94.50% backend
coverage**. Ruff formatting/lint, Oxlint, mypy, TypeScript, Python wheel/sdist and
Vite production build pass. No new GUI dependency is introduced in headless core.

Real headless Chrome on macOS used a fresh isolated server/database with actual
InMemoryTransport captures, not fabricated production API responses. Passed:
navigation, TX filtering/search, keyboard packet activation, Decoded/HEX/Parsing,
JSON download and exact raw representation, pause/resume, 390px overflow check,
watchdog offline dialog/recovery without reload, and confirmed Clear. No page errors.
Screenshots were inspected locally. Physical devices, RF delivery, Pi performance,
screen readers and Safari/Firefox are not claimed validated by this test.
