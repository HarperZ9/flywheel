# Source-mined Backend Matrix

- timestamp_utc: 2026-07-09T00:46:08.106525Z
- out_root: C:\dev\local-model\artifacts\source_mined_backend_matrix_user\20260709_004606
- providers_requested: dry, serve, ollama
- allow_online: False
- max_cases: 2
- rows: 3
- operational_rows: 3
- skipped_rows: 0
- mean_pass_rate: 1.0

| Provider | Backend | Live | Operational | Skipped | Cases | Pass rate | Response rate | Receipts | Mean latency ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dry | source-mined-dry | False | True | False | 2 | 1.0 | 1.0 | 1.0 | 0 |
| serve | source-mined-serve | True | True | False | 2 | 1.0 | 1.0 | 1.0 | 1 |
| ollama | source-mined-ollama:qwen2.5:7b | True | True | False | 2 | 1.0 | 1.0 | 1.0 | 851.5 |
