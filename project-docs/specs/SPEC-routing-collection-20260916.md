# Spec: M7 routing collection instrumentation

## Objective
Collect matched per-task routing evidence from the existing M7/local generation path without changing default scorecard or arm behavior. The collection is opt-in and records hashes, timings, identity provenance, oracle receipts, and fixed retrospective split assignment for built-in M7 task sets.

## Requirements
- [x] Preserve existing M7 scorecard output by default.
- [x] Built-in M7 task sets are always `retrospective_diagnostic`; no flag may relabel them fresh or final holdout.
- [x] Write a split-plan file before generation when collection is requested; its hash proves implementation ordering only.
- [x] Leave future fresh task-family manifests and group-level splits unavailable in the built-in path.
- [x] Record source/task/oracle identity hashes sufficient to detect changed prompt/task/test/oracle definitions without exposing hidden tests or solutions.
- [x] Record completion hashes from the text actually submitted to the oracle; do not expose raw hidden tests, solutions, or secrets.
- [x] Record timing denominators exactly: generation wall time, oracle wall time, candidate total wall time, and arm total wall time.
- [x] Record tokens only when a provider returned usage; otherwise null with `not_returned` provenance.
- [x] Record server-only time, dollar cost, and model digest as null when unavailable, never zero.
- [x] Use the existing artifact/store path; no new platform.
- [x] Fail closed when collection rows do not match the written split plan, including unknown, missing, or duplicate task ids per arm.
- [x] Fail closed when a row's `arm_name` conflicts with the report arm key.
- [x] Reject routing collection, split-plan, and scorecard output path collisions before writing receipts.

## Technical approach
- Add `harness/routing_collection.py` for full SHA-256 helpers, task/oracle identity hashing, split-plan construction, and collection artifact construction.
- Extend `harness/search.py` candidate traces for multi-candidate arms.
- Extend `harness/eval.py` with `collect_detail=False` default and detailed traces only when requested.
- Add `--routing-collection-out`, `--routing-split-plan-out`, and `--routing-split-id` to `scripts/run_m7_eval.py`. Do not add a split-family flag for built-in M7.

## Files to modify
- `harness/routing_collection.py` - helper schema and hashing functions.
- `harness/eval.py` - optional detailed arm/candidate traces.
- `harness/search.py` - optional per-candidate generation/oracle timing and metadata.
- `scripts/run_m7_eval.py` - opt-in collection CLI plumbing and artifact/store copy.
- `tests/test_eval.py` - focused trace coverage.
- `tests/test_routing_collection.py` - split plan and collection behavior.
- `project-docs/specs/SPEC-routing-collection-20260916.md` - this spec.

## Success criteria
- [x] Focused tests prove default scorecard compatibility.
- [x] Focused tests prove collection rows contain prompt/completion/task/oracle hashes and timing denominator labels.
- [x] Focused tests prove built-in split assignment is retrospective diagnostic and future fresh task-family manifest is unavailable.
- [x] Focused tests prove split/report consistency fails closed instead of assigning fallback metadata, accepting duplicate report rows, or accepting incomplete report arms.
- [x] Focused tests prove output path collisions are rejected before routing receipt writes.
- [x] No endpoint, training, download, or source-changing benchmark execution was required for the instrumentation implementation.

## Verification performed
- Red tests were observed before implementation for missing routing collection module, missing `collect_detail`, missing `per_task_detail`, and unrecognized routing CLI flags.
- Green focused verification: `python -m pytest tests/test_eval.py tests/test_eval_scorecard.py tests/test_routing_collection.py -q`.
- Green gates before PR preparation: `python scripts/check_file_gate.py`; `python scripts/check_verifier_stdlib.py`; `python scripts/check_public_instructions.py`; `python scripts/check_claim_language.py`; `python scripts/check_writing.py --gate README.md`; `python -m harness.cli_entry gate`; `python -m pytest tests/ -q`.

## Limitations
- Built-in M7 task sets remain retrospective diagnostic/evaluation material only; they are not clean training data and not a fresh final holdout.
- The split-plan hash proves that the implementation wrote a plan before generation for the run; it does not prove independent preregistration or untouched task provenance.
- Server-only latency, cost, and model digest stay null unless returned by the endpoint/provider.
- This change adds collection instrumentation only. The bounded local smoke used for acceptance is outside this source change and supports instrumentation readiness only; it is not model-quality, routing-quality, cost, latency, release, or competitor evidence.

## Status: IMPLEMENTED
