# Agentic Task-Set Adapter Plan

Date: 2026-07-09

Status type: adapter contract, not executable implementation.

Machine-readable adapter contract:

- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`

Source task set:

- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`

## Platform move

The custom task corpus now needs a boundary between "task definitions" and "benchmark execution." The adapter contract defines that boundary without running providers.

The adapter should produce a non-executing manifest first, then a scorecard only after a provider/harness actually runs or imports a task result.

## Proposed schemas

### `harness.agentic-task-manifest/v1`

Purpose: expand `harness.agentic-task-set/v1` into benchmark/profile/coverage-ready rows without execution.

Required fields:

- schema
- task_set_id
- task_count
- benchmark_ids
- dataset_lanes
- coverage_units
- expected_artifacts
- task_rows
- non_execution_guards

### `harness.agentic-task-scorecard/v1`

Purpose: store executed or imported task results.

Required fields:

- schema
- run_id
- task_set_id
- provider
- provider_role
- harness
- model
- rows
- artifact_paths
- limitations

Required row fields:

- task_id
- benchmark_id
- coverage_unit
- dataset_lane
- provider_role
- status
- failure_class
- metrics
- raw_prompt_path
- raw_output_path
- receipt_path

## Benchmark profile integration

The adapter maps the twelve task ids into benchmark ids:

- `toolchain_failure_recovery_matrix`
- `forum_ledger_deep_verify_scaling`
- `cross_harness_reproducibility_matrix`
- `local_resource_pressure_14b_32b`
- `tool_enterprise_readiness_matrix`
- `guardrail_accountability_friction`
- `closed_loop_agentic_gauntlet`

The profile manifest should consume the manifest artifact as an existing benchmark contract input, then expose each task id as a coverage unit.

## Coverage integration

Benchmark coverage should treat `harness.agentic-task-scorecard/v1` as an observed scorecard schema. Coverage should be complete only when expected task ids have rows for the required provider roles and metrics.

Missing task ids should remain missing evidence, not inferred failures.

## Closed-loop seed integration

Recommended preflight step:

- `agentic_task_manifest`: expand the JSON task corpus into a non-executing JSON/Markdown manifest.

Recommended focused execution step:

- `agentic_task_focused_scorecard`: run or import focused custom task results after explicit execution approval.

The focused step should not be a default live provider call until the dry plan and endpoint profiles are coherent.

## Outcome integration

Outcome synthesis should summarize:

- task count
- provider roles
- benchmark ids
- dataset lanes
- coverage units
- pass rate when rows exist
- failure classes
- artifact paths
- limitations

If only the manifest exists, outcome must say the custom task set is planned but not executed.

## Next implementation step

Implement `scripts/run_agentic_task_set_manifest.py` as a zero-provider, zero-endpoint command that reads:

- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`
- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`

and writes:

- `agentic_task_manifest.json`
- `agentic_task_manifest.md`

Tests-first validation is required before production code is added.

