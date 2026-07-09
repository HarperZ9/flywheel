# Cross-Harness Adapter Contract

Date: 2026-07-09

Status type: adapter contract, not executed benchmark evidence.

Machine-readable contract:

- `C:\dev\local-model\benchmarks\cross-harness-adapter-contract-v1.json`

## Decision

Use a shared adapter contract to make Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null providers consume the same task set and emit comparable receipts.

The tradeoff is stricter input/output discipline up front in exchange for benchmark results that can be compared without re-litigating whether the providers ran the same task.

## Current evidence

Observed local evidence for this contract:

- `C:\dev\local-model\harness.cmd` exists.
- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json` exists.
- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json` exists.
- `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop` exists.
- `E:\local-model-run` exists.

`index.index_context_envelope` remains unavailable in this session with `Transport closed`, so this contract is grounded in targeted local checks and existing artifacts rather than a fresh Index map.

## Provider roles

| Provider role | Harness id | Target | Current state |
| --- | --- | --- | --- |
| `codex_harness` | `codex` | `5.3-Codex-Spark` | Contract-only; local harness entrypoint observed. |
| `flywheel_harness` | `flywheel` | `5.3-Codex-Spark` | Contract-only; closed-loop scripts exist in local harness. |
| `claude_code` | `claude_code` | operator-configured | Needs discovery; no local execution evidence recorded here. |
| `opencode` | `opencode` | operator-configured | Root observed; adapter still needed. |
| `local_14b` | `local_endpoint` | `14B` | Local model root observed; endpoint profile/gate still needed. |
| `local_32b` | `local_endpoint` | `32B` | Local model root observed; endpoint profile/gate still needed. |
| `dry` | `dry_null` | none | Planned for command and receipt verification. |

## Scorecard row contract

Every executed or imported row must include task set id, task id, benchmark id, coverage unit, provider role, harness id, model id, execution mode, status, failure class, raw prompt hash, raw output hash, raw prompt path, raw output path, receipt path, tool trace path if available, metrics, and limitations.

## Comparability rules

Rows are comparable only when task set id, task id, raw prompt hash, metric schema, compatible execution mode, and normalized provider role match.

Executed rows also need receipt path, raw output hash, and limitations or failure class when skipped or failed.

## Artifact layout

```text
C:/tmp/cross_harness_runs/<run_id>/<provider_role>/<task_id>/
  prompt.txt
  output.txt
  tool_trace.json
  receipt.json
  metrics.json
  limitations.md
```

## Non-execution boundary

This contract does not run any provider. It does not prove Codex, Flywheel, Claude Code, OpenCode, 14B, or 32B performance.

It defines the receipt shape required before those runs can be compared honestly.

## Next action

Implement a non-executing cross-harness manifest generator that expands the custom task set into provider/task receipt skeletons. After that, run dry/null rows before any live provider or endpoint execution.

