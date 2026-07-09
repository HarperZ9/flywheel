# Source-mined Backend Matrix

- timestamp_utc: 2026-07-09T01:41:22.097328Z
- out_root: C:\dev\local-model\artifacts\source_mined_backend_matrix_user\latest_run\20260709_014106
- providers_requested: dry, serve, ollama
- allow_online: True
- max_cases: 2
- rows: 3
- operational_rows: 3
- skipped_rows: 0
- mean_pass_rate: 0.833
- mean_quality_score: 0.728
- mean_reliability_score: 1.0

| Provider | Backend | Live | Operational | Skipped | Cases | Pass rate | Quality | Reliability | Response rate | Error rate | Timeout rate | Receipts | Mean latency ms | Failure classes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| dry | source-mined-dry | False | True | False | 2 | 0.5 | 0.435 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 0 | none:2 |
| serve | source-mined-serve | True | True | False | 2 | 1.0 | 0.879 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 17.5 | none:2 |
| ollama | source-mined-ollama:qwen2.5:7b | True | True | False | 2 | 1.0 | 0.869 | 1.0 | 1.0 | 0.0 | 0.0 | 1.0 | 7912.5 | none:2 |
