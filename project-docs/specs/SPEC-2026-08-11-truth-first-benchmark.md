# Spec: Truth-first lane repair and cross-harness benchmark baseline

## Objective

Make Flywheel's lane-health surface report live runtime truth, then produce a
re-checkable Codex-versus-Flywheel orchestration baseline using the existing
four-task cross-harness contract. Execute every reachable configured route and
preserve unavailable routes as typed blocked evidence.

## Canonical design

`docs/superpowers/specs/2026-08-11-truth-first-benchmark-design.md`

## Requirements

- [ ] Source checkout paths resolve from an explicit or inferred workspace root
      without duplicated container segments.
- [ ] Command resolution, source presence, and source-profile installation use
      one source-repository resolver.
- [ ] Source command resolution returns a child launch specification with
      argument vector, working directory, and bounded environment overrides.
- [ ] Python source lanes use child-only working directory and `PYTHONPATH`
      settings; Node source lanes use an absolute script path.
- [ ] `flywheel lanes --probe` forwards the live-probe request.
- [ ] A present source checkout is probed even when the global package is
      absent.
- [ ] Presence-only and live-probed rosters are distinguishable in JSON and
      text.
- [ ] Failed probes remain non-live and carry exact failure detail.
- [ ] The missing cross-harness executor and deterministic oracles implement the
      existing manifest and execution contract.
- [ ] Execution, oracle, and receipt states remain orthogonal, with an explicit
      precedence for the compact primary outcome.
- [ ] Only verified, well-formed rows with an oracle pass or fail enter the
      deterministic quality denominator.
- [ ] Latency and resource summaries name the included statuses and sample
      count; unavailable attempts never enter performance denominators.
- [ ] The admission smoke runs before the Spark pilot.
- [ ] The pilot uses `agt-001`, `agt-003`, `agt-009`, and `agt-010`, two Spark
      roles, and three repetitions, for 24 planned rows.
- [ ] The separate local baseline uses the same four tasks, `local_14b` and
      `local_32b`, and one repetition, for eight planned rows.
- [ ] Configured 14B and 32B routes are freshly gated; each planned row is
      executed or recorded as typed unavailable.
- [ ] The 84-attempt expansion is blocked until every pilot acceptance gate
      passes.
- [ ] Raw artifacts and reports preserve commands, hashes, denominators,
      resource/usage nulls, failures, receipts, and re-check verdicts.
- [ ] Creative, shader, website, deployment, publication, and outreach surfaces
      remain untouched.

## Technical approach

1. Add failing lane and CLI regression tests.
2. Centralize source-checkout resolution and route every source consumer through
   it.
3. Add a source-aware child launch specification to MCP transport, then make
   probe intent flow from CLI to roster to that execution path.
4. Add failing executor/oracle contract tests using offline fixtures.
5. Implement the missing executor, deterministic oracles, CLI/script surface,
   and the minimum existing-synthesizer changes.
6. Run repository gates, then capture a before/after lane roster.
7. Generate fresh endpoint/auth gates and the two-task admission smoke.
8. Run or honestly block the 24-row Spark pilot and configured local rows.
9. Generate comparison, coverage, outcome, integration-map, methodology, and
   conclusion artifacts.
10. Request independent code and evidence review before accepting the baseline.

## Expected files to modify

- `harness/lanes.py` - shared source resolution and live-probe truth.
- `harness/mcp_client.py` - child-only working directory and environment launch
  support.
- `harness/cli_entry.py` - probe forwarding and executor command exposure.
- `harness/context_envelope.py`, `harness/gateway.py`,
  `harness/lane_caller.py`, and runtime paths in `harness/plugins.py` - retain
  source-aware launch fields without leaking them into public rosters.
- `tests/test_lanes.py` - resolution and probe regression coverage.
- `tests/test_mcp_client.py` - launch-spec transport coverage.
- `tests/test_harness_cli.py` - CLI forwarding and help contract.
- `benchmarks/agentic-task-set-v1.json` - portable pilot inputs and oracle
  declarations.
- `benchmarks/fixtures/cross-harness/*.json` - fixed raw task facts from which
  oracles independently derive expected results.
- `benchmarks/cross-harness-adapter-contract-v1.json` - public-clean execution
  contract and orthogonal state fields.
- `harness/cross_harness_executor.py` - manifest-driven attempt execution.
- `harness/cross_harness_types.py` and `harness/cross_harness_artifacts.py` -
  sub-300-line typed boundaries, isolated workspaces, and receipt material.
- `harness/cross_harness_adapters.py` - injected Codex, Flywheel, and local
  provider adapters kept below the file-size gate.
- `harness/cross_harness_cli.py` - packaged executor entrypoint.
- `harness/cross_harness_seed_steps.py` - focused seed-orchestrator step
  construction without growing the frozen seed runner.
- `harness/cross_harness_oracles.py` - deterministic task checkers.
- `scripts/run_cross_harness_execution.py` - operator entrypoint.
- `scripts/run_closed_loop_benchmark_seed.py` - canonical ownership and
  orchestration of the existing closed-loop seed schema.
- `tests/test_cross_harness_executor.py` - attempt/failure/receipt contracts.
- `tests/test_cross_harness_artifacts.py` - workspace, path, source-integrity,
  and artifact-index contracts.
- `tests/test_cross_harness_seed_steps.py` and
  `tests/test_closed_loop_benchmark_seed.py` - admission/Spark/local ordering
  and seed/result ownership.
- `tests/test_cross_harness_adapters.py` - provider command and trace contracts.
- `tests/test_cross_harness_oracles.py` - deterministic oracle contracts.
- `harness/adapter_runtime_matrix.py` - endpoint-gate-aware readiness if needed.
- `harness/cross_harness_manifest.py` - execution-ready manifest fields if
  existing fields are insufficient.
- `scripts/run_cross_harness_manifest.py` - repository-relative defaults.
- `scripts/run_adapter_runtime_matrix.py` - endpoint-gate input.
- `scripts/run_benchmark_profile_manifest.py` - scoped runnable pilot profile.
- `scripts/run_benchmark_profile_coverage.py` - executed-row completeness.
- `scripts/run_benchmark_execution_matrix.py` - executor ordering and blocked
  expansion gate.
- `scripts/run_cross_harness_integration_map.py` - runtime artifact topology,
  status, and hash map generated before drift.
- `scripts/run_harness_cli.py` - generated CLI/help contract.
- `scripts/run_harness_comparison_report.py` - real attempt consumption.
- `scripts/run_closed_loop_outcome_report.py` - baseline signal consumption.
- `harness/schematic_drift.py` and the existing integration graph - executor
  topology and drift checks.
- `tests/test_cross_harness_integration_map.py` - required runtime inputs,
  schema, hashes, and generation order.
- Existing related tests for every modified consumer.

The implementation must shrink this list when existing interfaces already
satisfy the contract. Any new file or schema outside this list requires a spec
update before code changes.

## Success criteria

- [ ] Focused lane/CLI tests fail before and pass after the repair.
- [ ] No resolved command contains a duplicated `public/public` segment in the
      current source layout.
- [ ] A fresh live roster reports probe-derived, not install-derived, status.
- [ ] Executor fixture tests cover every typed outcome and receipt tampering.
- [ ] Both synthesizers consume generated attempt artifacts.
- [ ] Admission smoke completes or emits valid unavailable rows for each target
      role.
- [ ] The pilot produces 24 planned Spark rows with a complete availability
      denominator.
- [ ] The separate local baseline produces eight planned rows that name exact
      model, backend, and gate state and do not enter the Spark comparison.
- [ ] Every completed attempt has an oracle result and re-checkable receipt.
- [ ] Full tests and public repository gates pass.
- [ ] Final reports include raw artifact paths, methodology, metrics,
      limitations, and next action.
- [ ] Independent review returns specification pass and quality approval.

## Blockers

- Live Codex authorization and `5.3-Codex-Spark` availability are unknown until
  the admission probe runs.
- Flywheel-role access to the same requested model is unknown until its adapter
  and authorization gates run.
- Local 14B and 32B endpoint availability is unknown until fresh endpoint gates
  run.

These are expected benchmark outcomes, not reasons to fabricate rows or delay
the integration report. Each becomes executed or typed unavailable evidence.

## Status: APPROVED

Approved in conversation on 2026-08-11. Implementation planning expanded the
expected-file list only where the approved integration-map, denominator, and
portable-input requirements already require an existing consumer to change.
