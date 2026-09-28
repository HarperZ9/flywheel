# Incident-sim process-audit desktop review

The Receipts workspace includes a native review card for saved incident-sim
process-audit JSON. It accepts either the inner
`flywheel.incident-sim-process-audit/v1` packet or an outer command report that
contains `audit_packet`; in the outer case the card extracts the inner packet
and sends only those JSON bytes to:

```text
POST /api/incident-sim/process-audit/review
```

The review is read-only. It does not request a Journey grant, save the packet,
read paths in the browser, or mint any receipt. The desktop client shows the
source SHA-256 and byte count over the exact uploaded bytes, then renders packet
integrity separately from semantic and access claims.

Labels are intentionally bounded:

- `Packet integrity` means packet-local digest and receipt checks.
- `Semantic UNVERIFIABLE` means the review does not prove task, trace, scorer,
  or access truth.
- `Declared access coverage` means retained declared records were checked
  against the packet inventory. It does not establish actual lab access.
- `Reported coverage` is copied packet data and is shown separately when the
  declared access component drifts.

Each reported source pointer expands to the JSON pointer, full source value, and
the local source location with line, column, byte offset, and context from the
bytes the client uploaded.
