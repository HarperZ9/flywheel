# Candidate-prefix invocation accounting

The local finalizer experiment shares one candidate prefix across C, A and B.
C scores that candidate. A and B each may invoke a finalizer. Summing verdict
rows omits prefix work; charging the prefix to every arm counts it three times.

Add `--record-invocations` to
`scripts/run_local_finalizer_candidate_prefix_experiment.py` to write an
accounting manifest, per-prefix/per-finalizer receipts and
`primary/invocation-accounting.json`. Existing invocation defaults and historical
artifacts remain unchanged. The new aggregate is also included in the run summary
and CLI JSON. Use it instead of the legacy `model_calls_after_prefix` row field,
which describes finalizer runner entries and is not a transport counter.

The manifest declares every normal/A/B stage before execution. Each task's three
rows reference the same prefix identity. An explicit skip establishes that an
arm was not dispatched; a missing receipt is incomplete coverage. Generated run
UUIDs distinguish repeated runs with identical tasks and outputs. One repetition
is supported. Unsafe and case-fold duplicate task names are rejected.

The CLI binds task-set and contract file hashes, safe profile/model labels and
the profile hash when available. Fixture and executing-harness Git revisions
and dirty states are separate. A Git revision does not pin dirty or ignored
runtime bytes, dependencies, or endpoint state. Python callers can supply these
bindings explicitly; absent or unsafe values are null. No profile URL or private
configuration is copied into this accounting manifest.

`known_started_invocations` is a lower bound. `total_started_invocations` is
nullable and becomes exact only when planned stage dispositions, event sequences
and invocation terminals are complete. Returned, raised and unknown outcomes are
separate. Missing usage remains unknown per native field; requested output token
ceilings are not consumed tokens. A valid accounting receipt does not establish
task correctness or authentic external provenance.

Python callers explicitly pass the same `ExperimentAccounting` object to
`LocalCandidatePrefixRunner(..., accounting=context)` and
`run_candidate_prefix_experiment(..., accounting=context)`. Existing callback
signatures are unchanged. Uninstrumented callbacks have unavailable observation;
returned counters or model histories are never treated as replacement receipts.

The optional context `transport_factory` accepts `observer=` and returns the
existing four-argument transport callable. It is intended for the separately
reviewed strict local HTTP factory. The normal default backend is not silently
replaced. Without that explicit transport observation, network-attempt totals
are null even when proposer invocation counts are exact. Observation covers the
injected backend stage, not unrelated process/network activity or earlier probes.

Transport UUIDs are bound to their parent invocation. Connection/send phase
markers are pre-syscall intent. Terminal progression records attempted local I/O,
not receiver acceptance. A truncated intent stream leaves the send outcome
unknown. A completed typed preflight rejection can establish no I/O; an empty
event stream alone cannot. Distinct retry attempts are counted separately if an
injected backend supplies them; this module does not add retries.

Starts are persisted before delegate execution. A recorder failure latches the
whole run against further dispatch, including when a backend normalizes the error.
A failure after possible transmission does not claim prevention or cancel remote
computation. Receipts may be incomplete after interruption; there is no automatic
resume or receipt reconstruction from old histories. Preserve old runs and write
separate corrections that identify inferred counts and unavailable wire usage.

Offline controls exercise omitted/tripled prefixes, identical-output identities,
prefix errors, skipped/missing stages, finalizer preflight, retry observations,
unpaired intent events, usage gaps, hash-valid malformed event sequences and fatal
recorder failures. The injected-backend CLI integration control compares identical
request payloads and unchanged task verdicts with accounting enabled and disabled.
No model call is required to test the accounting implementation.
