# Incident-sim evaluation and process-audit packet

This slice evaluates a synthetic, local incident task against a submitted trace.
It is a bounded fixture checker, not a general runner.

Public harness API:

```python
from harness.incident_sim_eval import evaluate_incident_sim
from harness.incident_sim_packet import build_process_audit_packet

evaluation = evaluate_incident_sim(task, trace)
packet = build_process_audit_packet(task, trace)
```

## Packaged command

From a checkout, try the synthetic examples:

```text
flywheel incident-sim --task examples/evaluation/incident-sim/task.json --trace examples/evaluation/incident-sim/matching-trace.json
flywheel incident-sim --task examples/evaluation/incident-sim/task.json --trace examples/evaluation/incident-sim/wrong-state-trace.json
```

The installed command also accepts local files outside a checkout. Add
`--expected-task-sha256` and `--expected-trace-sha256` to compare the exact input
bytes with previously recorded digests. Each input is bounded to 1 MiB.
The command emits JSON to stdout, including raw input hashes and byte lengths,
the evaluation and the process-audit packet. It posts nothing externally.

Exit `0` means the submitted trace matches the bounded fixture checks. Exit `1`
means drift, `3` means an unverifiable result, and `2` rejects input. Neither
exit zero nor an intact receipt proves that the submitted actions actually ran.
Packet hashes bind canonical JSON values; command source hashes bind the original
file bytes, including whitespace. Retain both files for review.

## Python API behavior

`build_process_audit_packet(task, trace, supplied_evaluation=None)` always
recomputes the evaluation from `task` and `trace`. A supplied evaluation is
compared and reported as matching or drifting; it is never trusted as assessed
truth.

## What it checks

The evaluator separates five facts that must not be collapsed:

- completion: the trace completed and names the expected task, fixture, spec,
  scorer and checker identities;
- correctness: ordered actions and final state match the fixture;
- enforcement: expected local block decisions are present;
- observation coverage: expected, observed, missing, duplicate, reordered and
  changed action payloads are reported separately;
- claimed-vs-checked scores: claimed scores are copied with source pointers, and
  the checked score is derived only from the deterministic local checker.

The local registered identities are pinned in code:

- checker: `incident-sim-local-checker` version `1`;
- scorer: `ordered-action-final-state` version `1`.

A task and trace that both name a different checker or scorer do not pass merely
because they agree with each other.

## Input boundary

Inputs are already-loaded JSON objects. The API does not read files, execute
commands, call a model, or access the network.

The top-level task and trace schemas are closed. Required fields must be present,
unknown top-level fields fail closed, action and score lists are bounded, and deep
input structures are rejected before sequence matching. Missing evidence becomes
`UNVERIFIABLE`; it cannot silently count as `MATCH`.

Malformed types, oversized lists, excessive depth, unknown top-level fields,
ambiguous expected enforcement rows, and invalid schema identifiers are
work-blocking validation failures. Packet construction raises a bounded
`IncidentSimValidationError` before receipts are reconstructed. Missing evidence,
such as a missing checker field, remains a supported `UNVERIFIABLE` evaluation
result.

The state and action payload comparisons use canonical JSON byte equality, so
Python truthiness does not turn `1` and `true` into the same value.

Enforcement is checked as an exact canonical row set. The report labels missing
expected decisions, unexpected observed decisions, duplicate observed rows, and
conflicting observed decisions per `action_id` separately. An empty observed
enforcement list only matches when the task explicitly expects no enforcement
events.

## Process-audit packet

The packet contains:

- `task_sha256`, `trace_sha256`, and `evaluation_sha256`;
- exact JSON pointers and source values for deciding task and trace facts;
- the recomputed evaluation;
- incident case and incident proposal objects built with the existing incident
  helpers;
- reconstructed action receipts, a work receipt, and an audit receipt built with
  existing receipt helpers;
- receipt verification results;
- roles, shared dependencies, and independence unknowns;
- limits and `does_not_prove` statements.

Action receipts are reconstructed from the submitted trace. They prove only that
the packet consistently sealed the submitted trace facts; they do not prove the
actions actually ran. Observation coverage is relative to the fixture's expected
actions, not the whole workstation.

The audit receipt is a bounded reviewer judgment chained to the work receipt. It
is not an independent external ground truth claim.

## What is not integrated here

This slice does not include live agent execution, Inspect runtime execution,
network access, EMET wire integration, or an EMET witness receipt. If an EMET
receipt is later attached, it should witness the packet bytes and keep integrity
separate from task correctness.

The incident projection is not a general redactor. Private operator inputs,
prompts, transcripts, and provider payloads should stay private unless another
reviewed boundary explicitly admits them.

## Synthetic examples

The examples under `examples/evaluation/incident-sim/` are synthetic fixtures:

- `task.json`
- `matching-trace.json`
- `wrong-state-trace.json`

They are not actual agent runs and do not identify a real incident. The matching
trace evaluates to `MATCH`; the wrong-state trace retains a claimed `PASS` score
but evaluates to `DRIFT` because the checked final state differs from the task.
