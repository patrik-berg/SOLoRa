# Protocol

Status: **design draft; no compatibility guarantee yet**.

Phase 1 is local-only and does not encode, transmit, or receive protocol messages. Creating threads and posts therefore produces no radio traffic. This document remains a boundary for Phase 2 rather than an implemented wire contract.

SOLoRa application messages will be independent of Meshtastic's transport API. A versioned envelope is planned with these logical fields:

- `version`: protocol schema version
- `message_id`: globally unique identifier used for deduplication
- `message_type`: operation such as thread or post creation
- `origin_node`: stable sender identifier
- `created_at`: UTC timestamp
- `thread_id`: related discussion thread when applicable
- `payload`: type-specific content

The encoded representation must respect Meshtastic payload limits. Chunking, acknowledgement, retry, ordering, expiry, and conflict behavior will be specified only after measurements on two real nodes.

## Meshtastic transport boundary

```text
SOLoRa application protocol
→ SOLoRa compact binary messages
→ Meshtastic Data.payload
→ Meshtastic MeshPacket / routing
→ LoRa
```

SOLoRa uses Meshtastic as transport and must not duplicate its routing, hop handling, or link-level delivery behavior. The transport adapter will place SOLoRa bytes in `Data.payload` using the appropriate `PortNum`; private development currently targets `PRIVATE_APP = 256`. Current official definitions specify a 233-byte maximum payload, a maximum hop limit of 7, and private port numbers 256–511. These are upstream constraints, not permanent SOLoRa constants: verify them against the supported official protobuf/firmware version before every protocol change.

Frame design must budget SOLoRa headers, content, and any fragmentation metadata within the actual `Data.payload` limit. Design work must also measure protobuf overhead and airtime and account for broadcast versus unicast, packet/request IDs, device queue priorities, channel utilization, and observed serial/TCP/BLE behavior.

## Acknowledgement semantics

- **Meshtastic ACK or routing response** reports a transport/routing result. It does not prove that SOL1 has reconstructed, validated, or stored the content.
- **SOLoRa `COMMIT_ACK`** is a future application message. SOL1 may emit it only after receiving all required content, validating it, and completing the durable database transaction.

SOLoRa application retries will eventually wait for `COMMIT_ACK` without recreating Meshtastic's own packet retry mechanism. Packet IDs and request IDs belong to the transport correlation layer; SOLoRa message IDs provide application-level idempotency and deduplication. Exact retry and timeout policy remains a measured Phase 2 design decision.

## Compatibility rules

- Unknown message types must be ignored safely, not crash a node.
- Duplicate `message_id` values must be idempotent.
- Parsers must reject malformed or oversized input before persistence.
- Protocol fixtures must accompany every wire-format change.
- Secrets, credentials, and private keys must never be carried in application messages.
- Protocol decisions must cite the checked official Meshtastic version or commit.

Security properties such as signing or encryption beyond the transport layer remain an explicit design decision for a later phase.
