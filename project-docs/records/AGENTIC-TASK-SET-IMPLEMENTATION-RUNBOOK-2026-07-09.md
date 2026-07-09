# Agentic Task-Set Adapter Implementation Runbook

Date: 2026-07-09

Status type: implementation-ready runbook, not implemented code.

Machine-readable plan:

- `C:\dev\local-model\benchmarks\agentic-task-set-implementation-plan-v1.json`

Source artifacts:

- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`
- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`

## Decision

Implement the custom task-set adapter as a metadata-only command first. The first command must expand task definitions into `harness.agentic-task-manifest/v1`; it must not execute providers, probe endpoints, read model weights, or infer benchmark success.

## Interface

New script:

```powershell
python scripts/run_agentic_task_set_manifest.py --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --adapter C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json --out C:/tmp/agentic_task_manifest.json --markdown-out C:/tmp/agentic_task_manifest.md --store-root C:/tmp/harness_file_store
```

New harness subcommand:

```powershell
.\harness.cmd agentic-tasks --out C:/tmp/agentic_task_manifest.json --markdown-out C:/tmp/agentic_task_manifest.md --store-root C:/tmp/harness_file_store
```

Planned output schema:

- `harness.agentic-task-manifest/v1`

Future executed-result schema:

- `harness.agentic-task-scorecard/v1`

## Files to touch during implementation

Production files:

- `C:\dev\local-model\scripts\run_agentic_task_set_manifest.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_manifest.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_coverage.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

Test files:

- `C:\dev\local-model\tests\test_agentic_task_set_manifest.py`
- `C:\dev\local-model\tests\test_harness_cli.py`
- `C:\dev\local-model\tests\test_benchmark_profile_manifest.py`
- `C:\dev\local-model\tests\test_benchmark_profile_coverage.py`
- `C:\dev\local-model\tests\test_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\tests\test_closed_loop_outcome_report.py`

Documentation files:

- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

## Tests-first sequence

1. Add `test_manifest_expands_all_task_rows_without_execution`.
2. Add `test_manifest_maps_tasks_to_benchmark_ids_from_adapter`.
3. Add `test_manifest_rejects_missing_required_task_fields`.
4. Add `test_benchmark_coverage_recognizes_agentic_task_scorecard_schema`.
5. Add `test_closed_loop_seed_includes_agentic_task_manifest_preflight`.
6. Add `test_outcome_summarizes_manifest_as_planned_not_executed`.

Do not implement production code before these tests exist. Do not run tests until validation execution is explicitly authorized in this session.

## Implementation order

1. Implement `scripts/run_agentic_task_set_manifest.py`.
2. Add `harness.cmd agentic-tasks` delegation.
3. Add closed-loop seed metadata-only preflight `agentic_task_manifest`.
4. Add `--skip-agentic-task-manifest`.
5. Extend benchmark profile to reference the manifest artifact and future scorecard schema.
6. Extend benchmark coverage to recognize `harness.agentic-task-scorecard/v1`.
7. Extend outcome synthesis to summarize manifest-only artifacts as planned and not executed.
8. Update docs and catalog.

## Non-execution guards

- No model provider calls.
- No local endpoint probes.
- No model weight reads.
- No benchmark execution.
- No task success claims from manifest generation.
- No secret, `.env`, token, credential, private key, or payload-body output.

## Verification gate

Current session constraints prevent running tests or validation without explicit authorization. The implementation runbook is ready; the next authorized coding step should start with tests-first changes, then execute only the targeted test slice after approval.

