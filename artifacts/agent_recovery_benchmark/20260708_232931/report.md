# Flywheel Integration Benchmark Outcome

- timestamp_utc: 2026-07-08T23:30:20.307205Z
- run_root: C:\dev\local-model\artifacts\agent_recovery_benchmark\20260708_232931

## Flywheel core

- spin turns: 1 tasks: 4
- spin pass_rate delta: 0.0
- spin cache_hit_rate delta: 0.0
- spin avg_oracle_calls delta: 0.0
- evolutionary closed monotone: True
- evolutionary open monotone: False
- inversion acceleration: True
- inversion floor preserved: True
- loop closure ratio: 0.889
- accountability: 1.0 (strawman 0.0)

## M7 comparisons

- codex frontier pass_rate: 1.0
- flywheel verified_inference pass_rate: 1.0
- codex pass delta vs existing: 0.0
- flywheel pass delta vs existing: 0.0
- flywheel verified-vs-single delta vs existing: 0.0

## Forum-derived custom benchmarks

- case artifact: C:\dev\local-model\artifacts\agent_recovery_benchmark\20260708_232931\forum_benchmark_cases.json
- sources: 4
- benchmark cases: 5
- ready cases: 5
- metric count: 22
- agent recovery case present: True
- agent recovery metrics: recovery_success_rate, silent_failure_rate, retry_budget_compliance, fallback_quality, receipt_completeness, p95_recovery_latency
- closed-loop role: forum context -> benchmark cases -> harness measurements -> model/router/tool uplift backlog -> smaller local model release evidence

## Executable agent-recovery benchmark

- scenarios: 6
- recovery_success_rate: 1.0
- silent_failure_rate: 0.0
- retry_budget_compliance: 1.0
- fallback_quality: 0.958
- receipt_completeness: 1.0
- p95_recovery_latency: 1745

## Backend-adapter recovery benchmark

- adapter: chat-backend
- provider: dry
- backend: dry-echo
- live: False
- operational: True
- skipped: False
- skip_reason: 
- scenarios: 6
- recovery_success_rate: 1.0
- silent_failure_rate: 0.0
- retry_budget_compliance: 1.0
- fallback_quality: 0.958
- receipt_completeness: 1.0
- p95_recovery_latency: 1745
- retry_use_rate: 0.5
- fallback_use_rate: 0.167
- typed_escalation_rate: 0.167
- fault_coverage: malformed_json, none, partial_result, rate_limit, stale_cache, timeout
