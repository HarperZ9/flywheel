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
