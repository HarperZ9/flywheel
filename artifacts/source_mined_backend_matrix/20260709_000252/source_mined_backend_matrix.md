# Source-mined Backend Matrix

- timestamp_utc: 2026-07-09T00:02:55.946404Z
- out_root: C:\dev\local-model\artifacts\source_mined_backend_matrix\20260709_000252
- providers_requested: dry, serve, ollama, codex, claude, opencode
- allow_online: False
- max_cases: 2
- rows: 6
- operational_rows: 3
- skipped_rows: 3
- mean_pass_rate: 1.0

| Provider | Backend | Live | Operational | Skipped | Cases | Pass rate | Response rate | Receipts | Mean latency ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dry | source-mined-dry | False | True | False | 2 | 1.0 | 1.0 | 1.0 | 0 |
| serve | source-mined-serve | True | True | False | 2 | 1.0 | 1.0 | 1.0 | 10 |
| ollama | source-mined-ollama:qwen2.5:7b | True | True | False | 2 | 1.0 | 1.0 | 1.0 | 1929.5 |
| codex |  | False | False | True | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| claude |  | False | False | True | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| opencode |  | False | False | True | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
