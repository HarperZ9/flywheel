# Codex/Flywheel Experimental Outcome - 2026-07-09

## Scope

Measured target: `gpt-5.3-codex-spark` through the authenticated Codex account path (`codex-plan`).

Comparison surfaces:
- Codex frontier single-shot arm.
- Flywheel verified-inference arm using the same Codex account-backed model.
- Local/free source-mined backend arms: dry, local serve, Ollama.

Operator budget note: GPT-5.5 Extra High is available for analysis and design work, but rows in this report are `gpt-5.3-codex-spark` unless explicitly labeled otherwise.

## Live M7 result

Artifact: `C:\tmp\m7_codex_spark_live_plan_n1.json`

Command:

```powershell
python scripts/run_m7_eval.py --frontier --frontier-all --frontier-providers codex --frontier-model gpt-5.3-codex-spark --frontier-modes plan --frontier-only --baseline-provider codex --baseline-modes plan --n-tasks 1 --out C:/tmp/m7_codex_spark_live_plan_n1.json
```

Observed:
- runtime: approximately `300.8s`
- `single_shot`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- `verified_inference`: `pass_rate=1.0`, `avg_oracle_calls=4.0`
- `flat_n`: `pass_rate=1.0`, `avg_oracle_calls=4.0`
- `no_search`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- `frontier_codex-plan`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- verdict: `verified_inference >= frontier_codex-plan` is `MATCH`
- verdict: `verified_inference >= single_shot` is `MATCH`

Interpretation:
- This proves the live Codex account endpoint is wired into the M7 harness.
- This proves same-task comparison between Codex single-shot and flywheel verified-inference arms.
- This does not prove uplift because the one-task run is ceilinged at `1.0` across all arms.

## Source-mined backend matrix

Artifact: `C:\tmp\source_mined_backend_matrix_live_codex_local_n2_v2\20260709_004659\source_mined_backend_matrix.json`

Command:

```powershell
python scripts/run_source_mined_backend_matrix.py --providers dry,serve,ollama,codex --allow-online --modes plan --model qwen2.5:7b --endpoint-model gpt-5.3-codex-spark --max-cases 2 --backend-timeout-seconds 120 --out-root C:/tmp/source_mined_backend_matrix_live_codex_local_n2_v2
```

Observed rows:

| Provider | Backend/model | Cases | Pass | Response | Receipts | Mean latency ms |
|---|---|---:|---:|---:|---:|---:|
| dry | `source-mined-dry` | 2 | 1.0 | 1.0 | 1.0 | 0 |
| serve | `Qwen2.5-Coder-14B-Instruct (base, nf4)` | 2 | 1.0 | 1.0 | 1.0 | 7 |
| ollama | `qwen2.5:7b` | 2 | 1.0 | 1.0 | 1.0 | 766 |
| codex | `codex-plan:gpt-5.3-codex-spark` | 2 | 0.5 | 1.0 | 1.0 | 69170 |

Codex failed case:
- `benchmark_task_quality_audit_v1`
- response present: true
- receipt complete: true
- error: none
- task_focus_score: `0.091`
- pass threshold: `>=0.1`
- latency: `110037ms`

Interpretation:
- Local/free paths currently outperform Codex/Spark on this two-case source-mined slice by pass rate and latency.
- Codex/Spark is operational and receipt-complete, but its account-backed startup and workspace tool context add significant latency.
- The Codex failure is quality/oracle-related, not endpoint-related.

## Fixes shipped during this experiment

- `codex-plan` now uses `codex.cmd exec` safely on Windows.
- Codex endpoint selection now passes `--model` and captures `--output-last-message`.
- Source-mined backend prompts are compacted to reduce account-backed latency.
- Backend timeout receipts preserve the requested model.
- `run_source_mined_backend_matrix.py` now separates local/Ollama `--model` from remote `--endpoint-model`.
- Invalid root metadata was removed from `C:\Users\Zain\.codex\hooks.json`; `codex doctor` no longer reports the hooks parse warning.

## Experimental conclusion

Current evidence supports:
- Codex account-backed `gpt-5.3-codex-spark` is connected to the harness.
- M7 live benchmark wiring works for Codex single-shot vs flywheel verified-inference.
- Source-mined backend comparison works across dry, local serve, Ollama, and Codex.
- Local/free paths are substantially faster on the first two source-mined cases.

Current evidence does not yet support:
- A meaningful M7 uplift claim for Codex/Spark, because the first live M7 run is ceilinged.
- Any claim that Codex/Spark beats local models on the source-mined slice.
- Claude Code/OpenCode parity, because those harness endpoints still need confirmed CLI paths.

Next required run:
- Widen M7 to non-ceiling tasks.
- Run source-mined matrix across more cases with `--backend-timeout-seconds 120` or higher.
- Add Claude/OpenCode once their local CLI commands are confirmed.
