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

Implemented types are `POST = 1` and `COMMIT_ACK = 2`; `WANT = 3` and `SYNC = 4` are reserved. A `POST` payload is a four-byte unsigned thread ID followed by 1–204 bytes of UTF-8 body text. `COMMIT_ACK` has no payload and correlates to the committed POST. This first version deliberately supports only single-frame posts; fragmentation and complete forum synchronization are deferred.

Message IDs are generated locally from 12 cryptographically random bytes. The receiver stores each accepted ID in `received_messages` in the same transaction as the post. Replays therefore do not create duplicates, but still receive a `COMMIT_ACK` so a lost acknowledgement can recover.

## Outbox and retries

Publishing through the sync service commits the post and encoded frame to SQLite together. Due user traffic is sent before background traffic. An unsuccessful or unacknowledged frame remains in the outbox and is retried after 2, 4, 8… seconds, capped at two minutes. There are no heartbeats or idle polling: **Normal state is silent**. An ACK only removes an item when its source matches the intended destination.

## Validation and compatibility

Parsers reject unknown versions/types, zero or malformed IDs, invalid UTF-8, invalid thread IDs, illegal correlations, and frames over 233 bytes before persistence. Every wire change requires updated fixtures under `protocol/fixtures/` and must retain safe handling of duplicates and malformed input.

## Sources checked for v1

Authoritative upstream checks on 2026-09-07 used Meshtastic protobuf commit `f008c45` (`mesh.proto`, `portnums.proto`) and Meshtastic Python commit `0539a96`. They confirm the current 233-byte payload limit, private PortNum range 256–511 with `PRIVATE_APP = 256`, and SDK ownership of packet IDs, destination, hop limit, ACK request, and queue priority. Recheck current official definitions before implementing the hardware adapter.

Secondary implementation references were TC2-BBS-mesh (`295fb35`), Supply Drop BBS (`4b008ae`), and MeshMonitor (`17c412b`). Supply Drop reinforced separating the application core from transports. TC2 demonstrated persisted IDs, SQLite, and serial/TCP operation, but SOLoRa chose compact binary frames and a durable scheduled outbox instead of delimiter text, fixed character chunks, or sleeps. MeshMonitor demonstrated official protobuf/PortNum dispatch; its node/status patterns remain for later work. No reference code or architecture was copied.
