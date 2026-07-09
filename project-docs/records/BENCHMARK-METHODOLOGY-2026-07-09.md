# Benchmark Methodology

Date: 2026-07-09

Status type: methodology contract, not a benchmark result.

## Purpose

Measure whether the Codex/Flywheel harness improves agentic performance across Codex, Flywheel, Claude Code, OpenCode, local endpoints, and the 14B/32B local model tracks.

## Required comparison principle

Every provider/harness comparison must use the same task set where practical. A score is not comparable if the task, tool permissions, endpoint mode, artifact root, or receipt format differs without being recorded.

## Provider roles

Required provider or harness roles:

- Codex harness with `5.3-Codex-Spark`.
- Flywheel harness with `5.3-Codex-Spark`.
- Claude Code pointed at the configured target endpoint where practical.
- OpenCode pointed at the configured target endpoint where practical.
- Local 14B endpoint.
- Local 32B endpoint.
- Dry/null provider for command and receipt verification.

## Metrics

Core metrics:

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

## Dataset lanes

The benchmark set should cover:

- source-mined codebase tasks
- agentic tool workflows
- adversarial receipt integrity
- endpoint release gates
- guardrail/accountability friction
- local resource pressure
- cross-harness reproducibility
- replayable causal-ledger deep verification

## Run tiers

| Tier | Purpose | Execution shape |
| --- | --- | --- |
| Dry | Prove command assembly and artifact paths. | No model/provider execution. |
| Focused | Run a bounded task subset across the highest-priority providers. | Shared artifact directory and store root. |
| Full | Run the full provider/task matrix. | Requires operator approval because it may be long-running or consume quota. |

## Required artifacts

Each accepted benchmark run should produce:

- raw provider/harness scorecards
- benchmark profile manifest
- benchmark execution matrix
- benchmark coverage report
- harness comparison report
- closed-loop seed report
- closed-loop outcome report
- run id and artifact directory
- limitations and failure-mode notes

The first custom task-set corpus is `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`, documented by `C:\dev\local-model\project-docs\records\AGENTIC-BENCHMARK-TASK-SET-2026-07-09.md`.

The adapter boundary for that corpus is `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`, documented by `C:\dev\local-model\project-docs\records\AGENTIC-TASK-SET-ADAPTER-PLAN-2026-07-09.md`.

Cross-harness comparability is governed by `C:\dev\local-model\benchmarks\cross-harness-adapter-contract-v1.json`, documented by `C:\dev\local-model\project-docs\records\CROSS-HARNESS-ADAPTER-CONTRACT-2026-07-09.md`.

## Validity rules

- Do not compare results across different task sets unless the difference is explicitly labeled.
- Do not treat missing provider output as failure unless the harness successfully invoked that provider and captured a provider-side failure.
- Do not treat command generation as benchmark execution.
- Do not claim endpoint readiness from root presence alone.
- Do not publish model claims without endpoint, benchmark, checksum, provenance, and model-card evidence.
- Do not claim causal-ledger scaling until `verify()`, `verify(deep=True)`, `checkpoint()`, warm storage, and cold storage are measured separately.
- Do not compare Codex, Flywheel, Claude Code, OpenCode, or local endpoint rows unless task id, prompt hash, metric schema, execution mode, provider role, and receipt requirements match the cross-harness adapter contract.

## Forum ledger scaling lane

Forum's replayable causal ledger needs a dedicated scaling lane because content-addressed redaction shifts the integrity problem from "can the chain prove order" to "how expensive is re-hashing every present body at scale." The lane should measure entry count, present payload bytes, redaction ratio, storage mode, cold reload cost, shallow verify, deep verify, checkpoint generation, and negative controls for tampered payloads.

Benchmark plan: `C:\dev\local-model\project-docs\records\FORUM-LEDGER-DEEP-VERIFY-BENCHMARK-PLAN-2026-07-09.md`.
