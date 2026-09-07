# Protocol

Status: **design draft; no compatibility guarantee yet**.

SOLoRa application messages will be independent of Meshtastic's transport API. A versioned envelope is planned with these logical fields:

- `version`: protocol schema version
- `message_id`: globally unique identifier used for deduplication
- `message_type`: operation such as thread or post creation
- `origin_node`: stable sender identifier
- `created_at`: UTC timestamp
- `thread_id`: related discussion thread when applicable
- `payload`: type-specific content

The encoded representation must respect Meshtastic payload limits. Chunking, acknowledgement, retry, ordering, expiry, and conflict behavior will be specified only after measurements on two real nodes.

## Compatibility rules

- Unknown message types must be ignored safely, not crash a node.
- Duplicate `message_id` values must be idempotent.
- Parsers must reject malformed or oversized input before persistence.
- Protocol fixtures must accompany every wire-format change.
- Secrets, credentials, and private keys must never be carried in application messages.

Security properties such as signing or encryption beyond the transport layer remain an explicit design decision for a later phase.
