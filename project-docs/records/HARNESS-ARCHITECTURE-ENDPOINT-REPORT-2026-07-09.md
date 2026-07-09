# Harness Architecture and Endpoint Report

Date: 2026-07-09

Scope: current Codex/Flywheel local-model harness architecture, executable surface, benchmark loop, and endpoint readiness path.

Status type: architecture/readiness report, not a completed endpoint benchmark.

## Observed architecture surfaces

Executable and orchestration surfaces:

- `C:\dev\local-model\harness.cmd`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

Benchmark and comparison surfaces:

- `C:\dev\local-model\scripts\run_benchmark_profile_manifest.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_coverage.py`
- `C:\dev\local-model\scripts\run_benchmark_execution_matrix.py`
- `C:\dev\local-model\scripts\run_harness_comparison_report.py`

Endpoint and release surfaces:

- `C:\dev\local-model\scripts\run_model_endpoint_profiles.py`
- `C:\dev\local-model\scripts\run_model_endpoint_gate.py`
- `C:\dev\local-model\scripts\run_model_release_readiness.py`
- `C:\dev\local-model\scripts\run_model_publish_plan.py`

Relevant external roots observed:

- `E:\local-model-run`
- `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop`
- `C:\dev\public\pubscan`
- `C:\tmp`

## Current harness shape

The current shape is a zero-dependency Python harness fronted by `harness.cmd`, with individual scripts producing JSON/Markdown artifacts and optional file-backed receipts. The closed-loop seed is the orchestration spine. It assembles command steps for:

- endpoint auth status
- executable manifest
- command registry
- benchmark execution matrix
- benchmark profile
- context inventory
- tool readiness
- tool hardening plan
- local model endpoint profiles
- local model endpoint gates
- model release readiness
- model publish plan
- gather readiness
- classifier-friction scorecards
- M7 source-mined scorecards
- M7 governed-agent scorecards
- UnisonAI stateful provider matrix
- benchmark coverage
- harness comparison

The outcome synthesizer is the reporting spine. It reads closed-loop seed artifacts or file-store run ids and extracts available signals into an experimental outcome report.

## Endpoint architecture

Current endpoint flow:

1. Profile available model roots and known endpoint configuration with `run_model_endpoint_profiles.py`.
2. Gate live endpoint health and one fixed generation with `run_model_endpoint_gate.py`.
3. Attach endpoint profile and gate artifacts to model release readiness with `run_model_release_readiness.py`.
4. Convert readiness evidence into a model naming/publish checklist with `run_model_publish_plan.py`.
5. Include endpoint and release signals in closed-loop outcome synthesis.

Important constraint:

- Endpoint gate failures are documented as partial evidence by default so the closed-loop seed can continue when local endpoints are offline.
- A strict release gate requires `--strict-exit`.

## Provider/harness comparison path

Current provider comparison path:

- Benchmark profile declares provider roles and metric weights.
- Benchmark execution matrix emits dry, focused, and full run tiers without executing benchmarks.
- Closed-loop seed can generate shared-run artifacts.
- Harness comparison can synthesize Codex-vs-Flywheel deltas from existing scorecards.
- Outcome synthesis can combine seed, benchmark, endpoint, and comparison artifacts.

Current limitation:

- The same task set has not yet been executed across Codex, Flywheel, Claude Code, OpenCode, and local endpoints in this report.
- Therefore, there is no valid performance conclusion yet for `5.3-Codex-Spark`, 14B, 32B, Claude Code, or OpenCode.

## Endpoint readiness matrix

| Surface | Path observed | Current status | Missing evidence |
| --- | --- | --- | --- |
| Local model run root | `E:\local-model-run` | Root exists. | Model inventory, weight checks, endpoint config, live health, generation result. |
| 14B track | Via endpoint/profile/release scripts | Scaffolded. | Model files, profile artifact, gate artifact, benchmark summary, model card. |
| 32B track | Via endpoint/profile/release scripts | Scaffolded. | Model files, profile artifact, gate artifact, benchmark summary, model card. |
| OpenCode harness | `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop` | Root exists. | Adapter/config proof and shared-task benchmark artifact. |
| Codex harness | `C:\dev\local-model\harness.cmd` | Executable wrapper exists. | Dry-plan and focused-run receipts. |
| Flywheel harness | Local-model closed-loop scripts | Scaffolded in current harness path. | Explicit Flywheel adapter proof and shared-task comparison artifact. |

## Architecture verdict

The current harness is best described as a reproducible artifact-and-receipt orchestration layer, not yet a fully proven multi-harness benchmark engine. The structure needed for the final loop exists in scaffolded form: command registry, benchmark contract, execution matrix, endpoint profiling/gating, release planning, and outcome synthesis.

The next maturity step is not more architecture. It is one controlled metadata-only run followed by one focused benchmark run, using the same artifact directory and store root, so the comparison and outcome reports have real evidence to summarize.

## Next executable gates

1. Run the closed-loop dry plan.
2. Run metadata-only preflights: context inventory, tool readiness, gather readiness, benchmark profile, benchmark execution matrix, endpoint profiles.
3. Run endpoint gate in non-strict mode for the configured local endpoints.
4. Run one focused closed-loop seed.
5. Generate benchmark coverage, harness comparison, and outcome reports from the same run id.

