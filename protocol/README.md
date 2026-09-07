# Protocol workspace

`PROTOCOL.md` is the normative human-readable specification for the experimental SOLoRa v1 application envelope.

- `fixtures/` contains canonical hexadecimal frames used by automated compatibility tests.
- `schemas/` is reserved for future machine-readable schemas if they add value; the current fixed binary layout is implemented directly by the codec.

Fixture names follow `v<version>-<message-type>.hex`. Files contain lowercase hexadecimal bytes followed by a newline. Update the codec, normative documentation, fixtures, and tests together whenever the wire format changes.
