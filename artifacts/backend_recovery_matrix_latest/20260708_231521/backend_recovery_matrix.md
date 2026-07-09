# Backend Recovery Matrix

- timestamp_utc: 2026-07-08T23:15:25.244271Z
- allow_online: False
- max_scenarios: 6
- retry_budget: 2
- fallback_enabled: True
- stale_recompute_enabled: True
- typed_escalation_enabled: True

## Summary

- providers: 6
- runnable: 3
- live: 2
- operational: 3
- skipped: 3
- total_scenarios: 18
- total_failures: 0
- fault_coverage: malformed_json, none, partial_result, rate_limit, stale_cache, timeout
- mean_recovery_success_rate: 1.0
- mean_receipt_completeness: 1.0
- silent_failure_rows: 0

## Providers

| Provider | Backend | Live | Operational | Skipped | Scenarios | Pass | Fail | Recovery | Retry | Fallback | Escalation | p95 ms | Receipts | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| dry | dry-echo | False | True | False | 6 | 6 | 0 | 1.0 | 0.5 | 0.167 | 0.167 | 1745 | 1.0 |  |
| serve | serve | True | True | False | 6 | 6 | 0 | 1.0 | 0.5 | 0.167 | 0.167 | 1745 | 1.0 |  |
| ollama | ollama:qwen2.5:7b | True | True | False | 6 | 6 | 0 | 1.0 | 0.5 | 0.167 | 0.167 | 1745 | 1.0 |  |
| codex |  | False | False | True | 0 | None | None | 0.0 | None | None | None | 0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |
| claude |  | False | False | True | 0 | None | None | 0.0 | None | None | None | 0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |
| opencode |  | False | False | True | 0 | None | None | 0.0 | None | None | None | 0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |

## Per-fault metrics

### dry

| Fault | Scenarios | Pass rate | Retry | Fallback | Escalation | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| malformed_json | 1 | 1.0 | 0.0 | 1.0 | 0.0 | 800 |
| none | 1 | 1.0 | 0.0 | 0.0 | 0.0 | 220 |
| partial_result | 1 | 1.0 | 0.0 | 0.0 | 1.0 | 440 |
| rate_limit | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 895 |
| stale_cache | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 440 |
| timeout | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 1745 |

### serve

| Fault | Scenarios | Pass rate | Retry | Fallback | Escalation | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| malformed_json | 1 | 1.0 | 0.0 | 1.0 | 0.0 | 800 |
| none | 1 | 1.0 | 0.0 | 0.0 | 0.0 | 220 |
| partial_result | 1 | 1.0 | 0.0 | 0.0 | 1.0 | 440 |
| rate_limit | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 895 |
| stale_cache | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 440 |
| timeout | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 1745 |

### ollama

| Fault | Scenarios | Pass rate | Retry | Fallback | Escalation | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| malformed_json | 1 | 1.0 | 0.0 | 1.0 | 0.0 | 800 |
| none | 1 | 1.0 | 0.0 | 0.0 | 0.0 | 220 |
| partial_result | 1 | 1.0 | 0.0 | 0.0 | 1.0 | 440 |
| rate_limit | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 895 |
| stale_cache | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 440 |
| timeout | 1 | 1.0 | 1.0 | 0.0 | 0.0 | 1745 |

