# Codex vs Flywheel Benchmark Comparison

Date: 2026-07-09

Status type: comparison report placeholder, not a completed comparison.

## Current state

The comparison machinery exists, but a valid Codex-vs-Flywheel result has not been produced in this report.

Current scaffolded surfaces:

- benchmark profile manifest
- benchmark execution matrix
- benchmark profile coverage
- harness comparison report
- closed-loop outcome synthesis

## Required comparison shape

The valid comparison must run:

- the same task set
- the same artifact schema expectations
- the same model selector where possible
- the same allowed tool surface
- the same receipt requirements
- the same timeout/resource policy

The comparison should use the cross-harness adapter contract at `C:\dev\local-model\benchmarks\cross-harness-adapter-contract-v1.json` so provider rows remain comparable by task id, prompt hash, metric schema, execution mode, provider role, and receipt path.

## Result table

| Dimension | Codex harness | Flywheel harness | Status |
| --- | --- | --- | --- |
| Task set | Not executed in this report. | Not executed in this report. | Missing evidence. |
| Model | Target is `5.3-Codex-Spark`. | Target is `5.3-Codex-Spark`. | Planned. |
| Tool-use success | No result. | No result. | Missing evidence. |
| Quality | No result. | No result. | Missing evidence. |
| Reliability | No result. | No result. | Missing evidence. |
| Latency/resource use | No result. | No result. | Missing evidence. |
| Receipts | No shared-run result. | No shared-run result. | Missing evidence. |

## Next gate

Run the focused closed-loop seed against the shared task set, then generate benchmark coverage, harness comparison, and outcome reports from the same run id.
