# Adapter runtime matrix - 2026-07-09

Status: implemented, not validated, not executed.

## Mechanism

`harness.adapter-runtime-matrix/v1` joins the cross-harness adapter contract with optional endpoint profile and endpoint auth metadata. It records whether each role is manifest-ready, focused-run-ready, endpoint-profile-ready, auth-ready, and which blocking gates remain.

## Scope

Runtime rows cover the existing cross-harness roles:

- `codex_harness`
- `flywheel_harness`
- `claude_code`
- `opencode`
- `local_14b`
- `local_32b`
- `dry`

## Non-execution posture

- No provider CLI calls.
- No endpoint probes.
- No model-weight reads.
- No token-store reads.
- No secret values emitted.

## Evidence flow

- `scripts/run_adapter_runtime_matrix.py` emits JSON/Markdown.
- `harness.cmd adapter-runtime` exposes the command.
- `scripts/run_closed_loop_benchmark_seed.py` includes `adapter_runtime_matrix` after endpoint profiles and before endpoint gates.
- `scripts/run_benchmark_execution_matrix.py` includes the matrix as a dry-tier step.
- `scripts/run_benchmark_profile_coverage.py` recognizes the schema as planned-only cross-harness evidence.
- `scripts/run_closed_loop_outcome_report.py` exposes `adapter_runtime_signals`.

## Next executable step

Run the targeted validation slice after approval, then generate the metadata-only matrix as part of the dry preflight bundle.
