# Native agent trace boundary v1

The operation result envelope remains `flywheel.gateway-operation-result/v1`.
Its `result` is a `flywheel.gateway-agent-projection/v1` metadata projection.
Progress uses the same projection schema, with state `running`. Clients render
the state and counts without looking for a copied `final`, tool output, or goal.

Fields: `schema`, `operation_ref`, `journey_ref`, `state`, `trace_ref`,
`record_count`, `trace_head_sha256`, `projection_sha256`, `omissions`,
`does_not_prove`. `projection_sha256` hashes all other projection fields using
canonical JSON. `trace_ref` is `agt_` followed by 32 lowercase hex digits, derived
from the owner, Journey, and operation binding. The trace head hashes the last
accepted private record, not the projection. Failed results also carry the fixed
existing `reason` code. Public progress never forwards router event dictionaries.
Optional `runtime` has exactly three nullable fields: `python` matches
`[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}`, `system` is Windows, Linux, or Darwin,
and `architecture` is AMD64, x86_64, arm64, aarch64, x86, or i686.
The projection digest includes `runtime` when present. It never forwards the
router's arbitrary raw platform string; the original remains private.

`omissions` contains fixed codes: `PRIVATE_CONTENT`, `CREDENTIAL_VALUES`, and
`UPSTREAM_OUTPUT_LIMITS`. Original retained ledger entries, source context,
request, progress, and final router result live in the private store. There is
no registration in the global `agent_runs` store and no source-bearing scaffold
or global countersign call. A completed process does not establish semantic
correctness, source truth, or unlimited retention of original subprocess output.

Records are immutable, hash chained, owner/Journey/operation bound, and written
through the pinned private artifact filesystem before their metadata is emitted.
Each ledger append is persisted before the next model/tool step. Interrupted or
cancelled runs retain the accepted prefix; recovery does not claim a final answer
exists. Each record is bounded to 8 MiB, a trace to 32 MiB and 2048 records. A size,
secret, or custody failure stops the run with a fixed failure; it never silently
truncates evidence. Credentials are excluded from private records too.
Each accepted record has a separate immutable count/head checkpoint. A missing
record, missing checkpoint, or gap fails closed, including an interrupted write
between the two files. The hashes do not detect rollback of both all records and
their checkpoints together; this is not an externally anchored append-only log.

Private reading requires trusted owner and Journey/operation context, checks the
binding and every record hash, and uses the same pinned filesystem. No route
accepts a user-supplied owner or arbitrary path. Lifecycle v1 history and older
sealed results remain readable. Private detail navigation uses
`GET /api/operations/<op_ref>/trace?ref=<agt_ref>&sequence=0`.
The existing authenticated operation route resolves the trusted owner and Journey.
Each response carries one original record (at most 8 MiB canonical JSON),
its hash, `record_count`, and `next_sequence` (null at the currently accepted end).
The detail schema is `flywheel.gateway-agent-trace-detail/v1`. These content-bearing
responses belong in the private detail UI, never global history or scaffold feeds.
Completed reads also compare the private chain head/count to the sealed projection.
`record_canonical_base64` carries the exact canonical bytes excluding only
`record_sha256`; clients hash the decoded bytes and compare the decoded object
to the displayed record. This preserves Python float spelling and Unicode without
requiring another language to reconstruct the canonical number representation.
The response budget is 36 MiB, accounting for the duplicated base64 material and
the gateway's JSON Unicode escaping. Fetch and render one record at a time.
Errors use existing operation codes: `AUTH_REQUIRED` (401), `INVALID_REQUEST`
(422), `NOT_FOUND` (404), and `STORE_COMMIT_FAILED` (500) for corrupt or unsafe
custody. Error messages contain no supplied paths, source content, or credentials.

Evidence records remain until the operator removes the private runtime state;
this change adds no automatic export, external fetch, or deletion policy.
Current upstream tools already bound retained output (including the default
4000-character tool-output cap). This trace preserves their recorded values;
it does not recover bytes discarded before ledger insertion.
