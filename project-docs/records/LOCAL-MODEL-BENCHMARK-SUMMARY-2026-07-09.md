# Local Model Benchmark Summary

Date: 2026-07-09

Status type: local model benchmark status, not a completed benchmark.

## Current state

The local model benchmark path is scaffolded but not proven by live endpoint results in this report.

Observed local model root:

- `E:\local-model-run`

Scaffolded scripts:

- `C:\dev\local-model\scripts\run_model_endpoint_profiles.py`
- `C:\dev\local-model\scripts\run_model_endpoint_gate.py`
- `C:\dev\local-model\scripts\run_model_release_readiness.py`
- `C:\dev\local-model\scripts\run_model_publish_plan.py`

## Model tracks

| Model track | Current state | Missing benchmark evidence |
| --- | --- | --- |
| 14B | Release and endpoint workflow scaffolded. | Endpoint profile, health probe, generation probe, agentic benchmark scorecard, checksums, model card. |
| 32B | Release and endpoint workflow scaffolded. | Endpoint profile, health probe, generation probe, agentic benchmark scorecard, checksums, model card. |
| Other local models | Not summarized in this report. | Inventory and endpoint profile. |

## Required local benchmark gates

1. Inventory model files without exposing secrets.
2. Generate endpoint profiles for 14B and 32B.
3. Run endpoint gate in non-strict mode to record availability.
4. Run focused agentic tasks through each available endpoint.
5. Record latency, reliability, tool-use, output quality, and receipt completeness.
6. Feed scorecards into benchmark coverage, harness comparison, and outcome synthesis.

## Current conclusion

No performance conclusion is valid yet for the 14B or 32B models. The harness can describe the intended endpoint path, but live model capability remains unmeasured until endpoint gates and agentic benchmarks are executed.

