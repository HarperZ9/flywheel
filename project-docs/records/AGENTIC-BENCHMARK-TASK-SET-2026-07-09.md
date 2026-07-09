# Agentic Benchmark Task Set

Date: 2026-07-09

Status type: benchmark corpus draft, not executed results.

Machine-readable task set:

- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`

## Purpose

This task set turns the roadmap's benchmark goals into concrete cases that can be run consistently across Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null providers.

## Coverage

The corpus covers:

- source-mined codebase work
- agentic tool workflows
- adversarial receipt integrity
- endpoint release gates
- guardrail/accountability friction
- local resource pressure
- cross-harness reproducibility
- forum replayable causal-ledger scaling

## Task inventory

| Task id | Lane | Purpose |
| --- | --- | --- |
| `agt-001-index-fallback-integrity` | agentic tool workflows | Pressure Index fallback receipts and degraded-match handling. |
| `agt-002-forum-deep-verify-scale` | replayable causal-ledger scaling | Measure forum `verify()`, `verify(deep=True)`, checkpoint, redaction, and storage scaling. |
| `agt-003-codex-flywheel-shared-task` | cross-harness reproducibility | Force same-task Codex-vs-Flywheel comparison. |
| `agt-004-local-14b-endpoint-gate` | endpoint release gates | Profile and gate 14B local endpoint readiness. |
| `agt-005-local-32b-endpoint-gate` | endpoint release gates | Profile and gate 32B local endpoint readiness. |
| `agt-006-mneme-enterprise-readiness` | agentic tool workflows | Assess mneme readiness and hardening gaps. |
| `agt-007-relay-enterprise-readiness` | agentic tool workflows | Assess relay readiness and hardening gaps. |
| `agt-008-plexus-enterprise-readiness` | agentic tool workflows | Assess plexus readiness and hardening gaps. |
| `agt-009-receipts-vs-guardrails-friction` | guardrail/accountability friction | Compare paired receipt/accountability and guardrail/classifier friction. |
| `agt-010-documentation-schematic-maintenance` | source-mined codebase tasks | Measure doc/schematic synchronization after changes. |
| `agt-011-opencode-adapter-readiness` | cross-harness reproducibility | Prepare OpenCode adapter readiness for shared-task runs. |
| `agt-012-local-resource-pressure` | local resource pressure | Measure bounded local 14B/32B pressure and graceful degradation. |

## Scoring posture

The task set uses the existing benchmark metrics:

- task completion
- quality
- groundedness
- tool-use success
- workflow state management
- reliability
- failure-mode clarity
- latency
- cost/resource use
- reproducibility
- accountability receipts

## Execution posture

No task in this corpus is a result by itself. A valid result requires:

- raw prompt and task id
- provider/harness id
- model id
- artifact directory
- run id
- receipt or ledger reference
- metric row
- failure-mode row when applicable
- raw output path
- coverage report inclusion

## Next gate

Wire `harness.agentic-task-set/v1` into the benchmark profile/coverage scripts or add a small adapter that converts this JSON into focused/full closed-loop seed inputs.
