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

The v1 message types are:

| Value | Name | Payload |
| ---: | --- | --- |
| 1 | `POST` | legacy local thread ID plus UTF-8 body; decoded for compatibility |
| 2 | `COMMIT_ACK` | empty; `correlation_id` names the durably processed frame |
| 3 | `WANT` | one to 16 typed 13-byte object references |
| 4 | `SYNC` | flags byte plus up to 15 typed object references |
| 5 | `THREAD` | UTF-8 title; envelope ID is the global thread ID |
| 6 | `SYNC_POST` | 12-byte global thread ID plus UTF-8 body |

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

The serial adapter sends the v1 frame unchanged as `Data.payload`. It uses the SDK's `sendData(data, destinationId, portNum=PRIVATE_APP, ...)`, requests a Meshtastic routing ACK for unicast only, sets `wantResponse=False`, and records the non-zero returned `MeshPacket.id` solely as a transport result. Incoming delivery is restricted to the official `meshtastic.receive.data.PRIVATE_APP` event and its raw `decoded.payload`. `ROUTING_APP` events cannot become SOLoRa frames. Recheck current official definitions and SDK behavior before changing this mapping.

Secondary implementation references were TC2-BBS-mesh (`295fb35`), Supply Drop BBS (`4b008ae`), and MeshMonitor (`17c412b`). Supply Drop reinforced separating the application core from transports. TC2 demonstrated persisted IDs, SQLite, and serial/TCP operation, but SOLoRa chose compact binary frames and a durable scheduled outbox instead of delimiter text, fixed character chunks, or sleeps. MeshMonitor demonstrated official protobuf/PortNum dispatch; its node/status patterns remain for later work. No reference code or architecture was copied.
