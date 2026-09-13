# Gateway Effect Evidence

Terminal gateway-agent projections may include an optional
`effect_evidence` block with schema `flywheel.gateway-effect-evidence/v1`.
The block is derived by the backend from the accepted owner-private
`AgentTrace` prefix. It is not accepted from a worker or from submitted
projection JSON.

Normal worker `flywheel.gateway-agent-projection/v1` output excludes
`effect_evidence`. The gateway derives the block only after worker projection
validation and terminal lifecycle binding. A worker-supplied or self-hashed
effect summary confers no authority and is rejected before publication.

The public block is content-free. It may report the retained observation count,
omission count, an all-observation digest, source record hashes, trace sequence
numbers, JSON pointers, and value digests. Reported witness or receipt summaries
are supported only from retained `result` records. They carry the source trace
sequence, record hash, payload kind, and digest of the reported block. They
summarize reported chain metadata; they do not independently verify that an
action executed. The block must not copy private paths, arguments, outputs, file
contents, credentials, or raw witness records. Authorized reviewers use the
existing private trace-detail route to inspect a source record.

`cancelled` and `completed` keep their process meaning. A retained post-tool
fingerprint shows that an effect was observed in the accepted trace prefix. It
does not prove rollback, effect absence, current filesystem state, semantic
correctness, or complete workstation observation.

Legacy terminal projections without `effect_evidence` remain valid. Absence of
the block means the compact summary is unavailable or older, not that no effects
were observed.

Offline packets must not treat packet-contained pointers, hashes, or a
self-consistent projection digest as independent retention or producer
authentication. Offline acceptance of `effect_evidence` requires the exact trace
records and terminal result to be recomputed. A continuity claim also requires an
expected terminal or result hash retained through a separate trusted channel.

## Offline process-audit review

The optional process-audit `gateway_effect` component carries the submitted
terminal result, lifecycle history, and trace records for offline rechecking.
The reviewer receives separate results for internal consistency, correspondence
with separately supplied expected hashes, recorded effect coverage, and semantic
correctness. Missing observations remain a coverage limit, even when all supplied
records are consistent.

The component contains private trace payloads. Its shape preview is not a
redacted export of those payloads. Review the actual content and access scope
before sharing the packet. Removing or changing records changes the evidence
being checked; do not present a redacted copy as the original byte identity.

The review response recomputes the content-free preview from the submitted
trace records. It never echoes the submitted preview as trusted display text.
Unknown record kinds are counted as malformed. The response labels this preview
as derived data; it is not an exact quotation of a retained source value.
The desktop keeps this preview content-free when expanded. An explicit
`Show private source context` action reveals the corresponding operator-uploaded
trace context with a private-source label and exact local source location.

The existing `flywheel incident-sim` command accepts either a prepared component
through `--gateway-effect-component` or all three source files through
`--gateway-terminal-result`, `--gateway-lifecycle-history`, and
`--gateway-trace-records`. Use `--verify-packet` for subsequent offline review.
Optional `--expected-gateway-terminal-result-sha256`,
`--expected-gateway-lifecycle-history-sha256`, and
`--expected-gateway-trace-records-sha256` compare separately supplied canonical
JSON hashes. They do not establish who retained those reference values.

The CLI and review HTTP route retain a 1 MiB input limit. Large live traces may
not fit this first offline transport; do not silently trim a trace to make a
continuity claim pass. See the [review API](incident-sim-process-audit-review-api.md)
for the wrapper format and source-pointer scope.
