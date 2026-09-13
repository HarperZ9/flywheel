# Institutional access component

`harness.institutional_access` is a bounded consistency checker for declared evaluator evidence access. It records what access a reviewer says was requested, granted, denied, unavailable, unknown or withdrawn, then checks that declaration against the retained source inventory supplied by the caller.

It does not execute code, fetch resources, contact a producer, expand private content, or decide whether a model answer or scorer is correct. A complete access assessment is coverage metadata for the declared review scope. It is not semantic support for the claim.

## API

```python
from harness.institutional_access import access_scope, assess_institutional_access

scope = access_scope(
    "scope-id",
    {"claim-id": ["task", "trace"]},
    {"task": task_json, "trace": trace_json},
)
report = assess_institutional_access(record, scope=scope, sources={"task": task_json, "trace": trace_json})
```

`access_scope()` binds a scope id, each claim's required source refs, and the SHA-256 inventory of retained source values. `assess_institutional_access()` validates a declared record against that scope and returns `flywheel.institutional-access-assessment/v1`. Passing `None` as the record returns `None`, which means no institutional-access assessment exists.

`harness.incident_sim_packet.build_process_audit_packet()` can optionally attach this report under `institutional_access`. Incident-sim is synthetic, so the wrapper labels that attachment as `synthetic_declared_access`. Ordinary incident-sim packets still carry no institutional-access assessment, and packet verification reports that field as `NOT_ASSESSED`.

When present, the component carries a `component_sha256`; `verify_process_audit_packet()` recomputes that digest and checks that the audit subject was built with the same institutional-access digest. The packet verifier also recomputes `evaluation_sha256`, packet `section_sha256` values, `packet_sha256`, and the action/work/audit receipt verifiers. This is packet-local integrity validation only. It does not re-fetch missing task or trace bodies, establish semantic correctness, or prove that a coherent local rewrite of every packet-local digest did not occur.

## Command workflow

The packaged incident-sim command can attach this component when both files are supplied:

```text
flywheel incident-sim --task task.json --trace trace.json --institutional-access access.json --institutional-access-scope access-scope.json
```

The command reads all four files with the same bounded JSON reader used for task and trace inputs, emits source byte lengths and SHA-256 hashes, and rejects unpaired access/scope options. Its stdout is an outer `flywheel.incident-sim-command/v1` report containing the inner `audit_packet`. Extract that inner packet as shown in `docs/INCIDENT-SIM-EVALUATION.md` before recheck, then run:

```text
flywheel incident-sim --verify-packet packet.json
```

Packet recheck reports `NOT_ASSESSED` for institutional access when the packet has no component. It verifies packet-local digests and receipt seals only; it does not fetch hidden sources or turn complete access coverage into semantic support.
The command and Python verifier share the same packet-specific receipt order reconstruction, so order-only JSON reserialization has the same verifier result in both entrypoints. The command still reports the exact packet file byte hash supplied for review.

## What is checked

- The record uses the `flywheel.institutional-access/v1` schema and exact keys.
- The record's `scope_sha256` matches the caller-bound access scope.
- The retained source inventory still matches the scope.
- Each event has a deterministic integer sequence and a unique event id.
- Latest event status for each required source determines declared coverage, while earlier requested or denied events remain in event history.
- A prior requested or denied event can precede a later grant; history is retained and latest state is reported separately.
- Source pointers resolve inside the retained source value and their declared `source_value` matches exactly by canonical JSON hash.
- Unknown, denied, unavailable or withdrawn latest status for a required source limits coverage.
- A granted source with no checked source pointer limits coverage.
- Redactions with `unknown`, `blocks_verification` or `weakens_coverage` impact limit coverage.

## What remains outside the boundary

The component does not establish wall-clock truth, disclosure completeness, immutable external history, absence of undeclared withdrawn events, absence of contests, or semantic correctness of the evaluated claim. A coherent rewrite of a local record and every external anchor is outside this assurance boundary. Use contest receipts for dissent and corrections rather than overwriting access history.
