# Backend Recovery Matrix

- timestamp_utc: 2026-07-08T22:55:23.288505Z
- allow_online: False
- max_scenarios: 0

## Summary

- providers: 6
- runnable: 3
- live: 2
- skipped: 3
- mean_recovery_success_rate: 1.0
- silent_failure_rows: 0

## Providers

| Provider | Backend | Live | Skipped | Scenarios | Recovery | Silent failures | Receipts | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---|
| dry | dry-echo | False | False | 6 | 1.0 | 0.0 | 1.0 |  |
| serve | serve | True | False | 6 | 1.0 | 0.0 | 1.0 |  |
| ollama | ollama:qwen2.5:7b | True | False | 6 | 1.0 | 0.0 | 1.0 |  |
| codex |  | False | True | 0 | 0.0 | 0.0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |
| claude |  | False | True | 0 | 0.0 | 0.0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |
| opencode |  | False | True | 0 | 0.0 | 0.0 | 0.0 | online provider skipped; pass --allow-online to run CLI/API backends |
