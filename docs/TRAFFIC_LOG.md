# Radio Traffic Log

**Traffic Log is passive and never creates radio traffic.** It observes SOLoRa
application frames, not general Meshtastic activity or an Application/System Log.
Opening, filtering, pausing, inspecting, clearing and exporting cannot send frames,
connect a radio, poll node state, replay traffic or alter forum/outbox/dedupe state.

## Use

Open **Trafiklogg** in the main navigation. The global Application watchdog remains
the only backend Online/Degraded/Offline model. Configure and explicitly connect a
node and confirm its channel in Settings first. With no traffic the log stays empty.
The current local forum does **not** automatically transmit its posts: the existing
long-running forum-sync service remains deferred. The log must not imply otherwise.

Filter TX/RX and implemented registry types, or search IDs, channels and decoded
text. Select a row's time (keyboard accessible) for Decoded, HEX and Parsing views.
Desktop has a left navigation and side details panel; narrow screens stack cards
and details. HEX preserves offsets and byte boundaries with horizontal scrolling.
Copy uses the browser clipboard; insecure LAN HTTP may require manual selection.

Pause freezes only the view; backend capture and local stream continue. Resume
shows retained buffered events. Rensa requires confirmation and clears this runtime's
diagnostic buffer for all viewers, never SQLite. Restart also loses this volatile
history. Export downloads the **whole current backend buffer**, not a filtered or
paused subset, as JSON with app/protocol versions, UTC export time, system name/role,
session, sequence, channel metadata and permitted raw HEX. Forum text can be private;
review exports before sharing. This unauthenticated MVP uses the same trusted-local-
network boundary as the forum; do not expose it to an untrusted LAN or internet.

## Capture and storage

`TrafficSink` accepts immutable `TrafficObservation` values. `TrafficBuffer` retains
1000 `TrafficEvent` values per process, evicting oldest. No per-packet database writes,
SDK packet dictionaries, config objects, PSKs or exception reprs are retained.
Capture is constant-size (one bounded frame), failure-isolated, uses a nonblocking
lock and may discard a diagnostic event on contention. This is not an audit trail
or a complete RF sniffer. Protocol processing never waits for a browser or parser.

`MeshtasticTransport.send` captures bytes passed unchanged to `sendData`, with the
actual selected local channel and SDK result. A rejected queue before `sendData`
creates no TX frame event. A send exception/invalid SDK result is `Transport error`;
the outcome may be uncertain, not necessarily unsent. `Sent` means local SDK
acceptance, never RF delivery or durable application storage.

RX capture follows existing source/destination, PRIVATE_APP, payload-size and
selected-channel filtering, but precedes SOLoRa decoding and receiver invocation.
Malformed permitted frames therefore remain visible. ROUTING_APP/text/telemetry,
other interfaces and other channels are excluded. No routing ACK tracking is added;
an observed COMMIT_ACK remains an application message, not a routing result.

The web-owned gateway attaches an RX-only observer to its existing explicitly
opened SDK connection after a valid node/name/index binding. Changing channel
detaches the old observer without closing the connection; disconnect removes it.
Old events retain their original channel metadata. It opens no second connection.
`create_transport(..., traffic_sink=buffer)` allows the existing SyncNode/hardware
harness to share that runtime buffer. A separately launched CLI has a separate
process/buffer and is not magically visible in the web process.

InMemoryTransport accepts the same sink for virtual tests, marked `in-memory`
without invented Meshtastic channel/PortNum metadata. Dropped virtual traffic
generates TX only; delivery/replay generates RX without changing deduplication.

## Decoder and privacy contract

Diagnostics reuse `MessageType`, `PacketEnvelope` and all six existing payload
decoders. No wire IDs, codecs, retry schedules or airtime policies change. The API
publishes implemented registry names; the frontend has no parallel wire registry.
Parsing occurs on the read side outside the capture lock. Raw HEX is the original
full envelope, not re-encoded text; display normalization by existing codecs cannot
change those bytes. Control messages expose typed object references and flags.

An explicit **allowlist** permits v1 types 1–6. New enum entries do not opt themselves
in. AUTH 12/13, all other unknown/unreviewed types, unknown versions and oversized
frames are hidden **before retention**, including IDs, raw and decoded content.
Their byte length and safe transport metadata remain visible. Known malformed v1
frames retain HEX with a generic parse error. Any future type/field carrying secrets
requires a reviewed redactor before diagnostics can display/export it; the default
is whole-payload hiding. User text is not scanned for arbitrary passwords: do not
put credentials in forum posts.

## Local live delivery

`GET /api/traffic/stream` is SSE: initial bounded snapshot, then ordered deltas at
up to one local update/second. Fifteen-second HTTP keepalive comments contain no
radio traffic. There are no per-client unbounded queues. Slow clients may miss
evicted diagnostics; this never triggers repair/replay. Session/revision/oldest
markers deduplicate reconnect overlap and propagate clear/eviction/restart.
EventSource reconnects automatically; a confirmed watchdog Offline closes it and
keeps the browser's rows, then reopens it when the backend returns.

`GET /api/traffic` reads a snapshot, `DELETE /api/traffic` clears diagnostics, and
`GET /api/traffic/export` downloads JSON. None has a radio command dependency.
This PR adds no packet injection, replay, resend, PCAP or permanent log database.

## Upstream and validation

The official [Python SDK interface](https://python.meshtastic.org/mesh_interface.html)
was rechecked on 2026-09-09 for the raw `sendData`/PRIVATE_APP callback boundary.
Supported SDK remains `>=2.7.11,<2.8`; protocol-critical mappings remain the pinned
SDK/protobuf revisions recorded in PROTOCOL.md. No third-party code was copied.

Run `make check` for hardware-independent parser, adapter, gateway, virtual network,
SSE, privacy and frontend tests. See [physical validation](MESHTASTIC_HARDWARE_TEST.md)
for remaining two-radio evidence. A log entry is not proof of actual RF delivery.
