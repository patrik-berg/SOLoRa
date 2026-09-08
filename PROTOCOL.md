# Protocol

Status: **experimental v1 implemented for the Phase 2 virtual transport**. It is not yet a stable compatibility contract.

## Transport boundary

```text
SOLoRa application protocol
→ SOLoRa compact binary messages
→ Meshtastic Data.payload (PortNum PRIVATE_APP during development)
→ Meshtastic MeshPacket / routing
→ LoRa
```

Meshtastic owns addressing, routing, hop limits, its transmit queue, and transport ACKs. SOLoRa owns application message IDs, persistence, deduplication, retries awaiting durable application acknowledgement, and later synchronization semantics. A Meshtastic ACK is only a routing result; a SOLoRa `COMMIT_ACK` means the receiver committed the complete item to SQLite.

## Version 1 envelope

All integers use network byte order. A complete frame must fit in the current official 233-byte `Data.payload` maximum.

| Offset | Size | Field |
| --- | ---: | --- |
| 0 | 1 | protocol version (high nibble), message type (low nibble) |
| 1 | 12 | non-zero 96-bit `message_id` |
| 13 | 12 | `correlation_id`; zero except for acknowledgements |
| 25 | 0–208 | type-specific payload |

## Version 1 message registry

The high nibble of byte 0 is the protocol version and the low nibble is the message type, so v1 has exactly 16 numeric slots. Values are allocated centrally in this table and are immutable once published. `Planned` and `reserved` values are documentation only: v1 decoders must continue to reject them until an implementation adds codecs, fixtures, validation, and tests. Removed types are never renumbered or reused.

| Value | Symbolic name | Status | Normal direction | Priority class | Short purpose |
| ---: | --- | --- | --- | --- | --- |
| 0 | — | Invalid | — | — | Sentinel; never valid on the wire. |
| 1 | `POST` | Implemented, legacy | Unicast | User | Compatibility frame using a node-local thread ID; no longer emitted for new synchronized posts. |
| 2 | `COMMIT_ACK` | Implemented | Unicast reply | Control, expedited | Confirms durable application processing named by `correlation_id`; never a Meshtastic routing ACK. |
| 3 | `WANT` | Implemented | Unicast | Background control | Requests missing typed objects advertised by a peer. |
| 4 | `SYNC` | Implemented | Unicast | Background | Exchanges compact, paged object inventories after an explicit sync request. |
| 5 | `THREAD` | Implemented | Unicast | Background repair | Transfers one requested immutable thread object. |
| 6 | `SYNC_POST` | Implemented | Unicast | User or background repair | Transfers a post using its thread's global ID. |
| 7 | `POST_FRAGMENT` | Planned | Unicast | User or background repair | Carries part of content that cannot fit one `Data.payload`; layout is not yet designed. |
| 8 | `WANT_FRAGMENT` | Planned | Unicast | Background control | Requests missing fragments without retransmitting complete content. |
| 9 | `STATUS` | Planned | Primarily unicast/piggybacked | Background | Conveys compact node or sync state, preferably attached to traffic already being sent. |
| 10 | `STATUS_BEACON` | Planned | Optional broadcast | Background | Rare, minimal status advertisement when measurements justify it. |
| 11 | `PRESENCE` | Planned | Unicast or optional broadcast | Background | Explicit presence only when useful; authenticated traffic should normally refresh `last_seen`. |
| 12 | `AUTH_REQUEST` | Planned | Unicast | Control | Reserves the start of a future authentication exchange; security design is deferred. |
| 13 | `AUTH_RESPONSE` | Planned | Unicast reply | Control | Reserves the response half of future authentication. |
| 14 | `PROTOCOL_INFO` | Planned | Unicast request/reply | Control | Negotiates or reports protocol capabilities without changing the envelope version. |
| 15 | `CORE_EXTENSION` | Reserved | — | — | Reserved core expansion slot `[15,15]`; no subtype or payload encoding is currently defined. |

Priority classes describe scheduling intent, not delivery guarantees. User traffic is `POST`, newly authored `SYNC_POST`, and future `POST_FRAGMENT`; it precedes repair work. Control traffic is acknowledgement, request, negotiation, and future authentication traffic; only latency-sensitive `COMMIT_ACK` is currently expedited. Inventory, requested-object repair, status, beacons, and explicit presence are background traffic. A retransmitted or repair-sourced `SYNC_POST`/fragment remains background even though it carries user content.

All implemented traffic is normally unicast. Broadcast is reserved only as an option for future small, measured `STATUS_BEACON` or `PRESENCE` frames; neither is authorized by this registry. **Normal state is silent**: no planned type creates a heartbeat requirement. Ordinary authenticated traffic should later refresh `last_seen`, `STATUS` should piggyback when possible, and any `STATUS_BEACON` must be compact, low-frequency, and governed by measured airtime/channel utilization. Authentication values reserve identifiers only; they define no security scheme.

New posts use `SYNC_POST`; the legacy `POST` layout remains readable so existing queued v1 frames are not invalidated. Threads and posts use globally unique 96-bit object IDs, avoiding unsafe assumptions that separate SQLite databases assign the same local integer IDs. `COMMIT_ACK` has no payload and acknowledges durable handling of any outbox frame. Content remains single-frame: a thread title is at most 208 UTF-8 bytes and a synchronized post body at most 196. Fragmentation is deferred until physical-radio measurements justify its byte and airtime cost.

Message IDs are generated locally from 12 cryptographically random bytes. The receiver stores each accepted ID in `received_messages` in the same transaction as the post. Replays therefore do not create duplicates, but still receive a `COMMIT_ACK` so a lost acknowledgement can recover.

## Outbox and retries

Publishing through the sync service commits the post and encoded frame to SQLite together. Due user traffic is sent before background traffic. An unsuccessful or unacknowledged frame remains in the outbox and is retried after 2, 4, 8… seconds, capped at two minutes. There are no heartbeats or idle polling: **Normal state is silent**. An ACK only removes an item when its source matches the intended destination.

## Explicit repair flow

Repair begins only when a caller invokes `request_sync(peer)`; idle nodes emit no inventory traffic.

1. The initiator queues paged `SYNC` inventories with a reply-request bit on the first page.
2. The peer compares typed `(kind, object_id)` references and queues batched `WANT` frames for unknown objects. It also queues its own inventory once.
3. A `WANT` receiver queues requested `THREAD` or `SYNC_POST` objects from local durable storage.
4. If a post arrives before its thread, the receiver persists a repair request for the thread and withholds `COMMIT_ACK`. The sender's unchanged outbox retry later resends the post.
5. Every control page and object remains queued until application `COMMIT_ACK`. Replayed frames are idempotent and re-acknowledged without duplicating data or requests.

`SYNC` holds 15 references because its one-byte flag plus fifteen 13-byte references uses 196 of 208 available payload bytes. `WANT` holds 16 references exactly. Larger inventories are paged; object content is not fragmented in this phase.

## Validation and compatibility

Parsers reject unknown versions/types/object kinds, zero or malformed IDs, duplicate or truncated reference lists, invalid UTF-8, invalid thread IDs, illegal correlations, and frames over 233 bytes before persistence. Every wire change requires updated fixtures under `protocol/fixtures/` and must retain safe handling of duplicates and malformed input.

## Sources checked for v1

Authoritative upstream checks on 2026-09-07 used Meshtastic Python SDK `2.7.11` (tag commit `19d0669`, current master `0539a96`) and protobuf `v2.7.22` (tag commit `940ac38`, current master `f008c45`). They confirm the current 233-byte payload limit, private PortNum range 256–511 with `PRIVATE_APP = 256`, and SDK ownership of packet IDs, destination, hop limit, ACK request, and queue priority.

The connection implementation was rechecked on 2026-09-08 against the official Python API/source. It uses `SerialInterface(devPath)` for USB/direct serial, `TCPInterface(hostname)` on the SDK's default TCP port for network nodes, pyserial `comports()` for platform-neutral endpoint discovery, `myInfo` for local node number, `getLongName()` for display identity, and `DeviceMetadata.firmware_version` when supplied. Missing optional metadata remains unknown rather than being inferred.

The serial adapter sends the v1 frame unchanged as `Data.payload`. It uses the SDK's `sendData(data, destinationId, portNum=PRIVATE_APP, ...)`, requests a Meshtastic routing ACK for unicast only, sets `wantResponse=False`, and records the non-zero returned `MeshPacket.id` solely as a transport result. Incoming delivery is restricted to the official `meshtastic.receive.data.PRIVATE_APP` event and its raw `decoded.payload`. `ROUTING_APP` events cannot become SOLoRa frames. Recheck current official definitions and SDK behavior before changing this mapping.

`PRIVATE_APP` identifies SOLoRa's application payload; it does not identify the encrypted Meshtastic channel. Every node has an explicit, locally persisted channel binding consisting of node ID, exact channel name, and local channel index. Transmission sets that index and reception rejects `PRIVATE_APP` packets reported on any other index. Nodes may bind the same channel name at different local indices. `solora-link` is only a recommended name, never a wire constant or automatic fallback. Channel discovery and cached-status reads emit no LoRa traffic, and SOLoRa never reads, stores, or returns PSKs.

USB, direct serial, and TCP/network are interchangeable local client connections below the same `Transport` boundary; they do not alter the v1 envelope, message registry, destination semantics, priorities, or channel filtering. Local SDK connectivity must be reported separately from mesh reachability. Device-list refresh and connection metadata reads do not authorize SOLoRa application frames, discovery beacons, or heartbeat traffic.

## Authority identity (planned)

System display names have no wire authority. In particular, `SOL1` is not a reserved name and must never imply Primary behavior. A future authoritative server is declared by `system_role = PRIMARY` and identified externally by its Meshtastic Node ID. `system_name` may accompany status only as optional display metadata.

A future `STATUS` or `STATUS_BEACON` design may carry role, Node ID, optional system name, protocol version, forum revision, and a server epoch/authority generation for failover. Its precise encoding, trust rules, and conflict handling remain unimplemented. This section allocates no new message ID and changes no v1 wire format. Any future discovery stays low-frequency or piggybacked so **Normal state is silent** remains true.

Secondary implementation references were TC2-BBS-mesh (`295fb35`), Supply Drop BBS (`4b008ae`), and MeshMonitor (`17c412b`). Supply Drop reinforced separating the application core from transports. TC2 demonstrated persisted IDs, SQLite, and serial/TCP operation, but SOLoRa chose compact binary frames and a durable scheduled outbox instead of delimiter text, fixed character chunks, or sleeps. MeshMonitor demonstrated official protobuf/PortNum dispatch; its node/status patterns remain for later work. No reference code or architecture was copied.
