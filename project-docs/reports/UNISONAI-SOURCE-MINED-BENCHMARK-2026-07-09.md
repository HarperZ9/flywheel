# UnisonAI Source-Mined Benchmark Integration

Date: 2026-07-09

Status: dataset, deterministic lanes, live provider matrix, stateful fixtures, provider-action fixture path, provider-selectable action matrix, and repair-gated action matrix implemented

## Source

- Repository: `https://github.com/MettaMazza/UnisonAI`
- Source type: public GitHub repository / README source lead

Observed public claims were used as benchmark pressure, not accepted as verified performance conclusions.

## Extracted benchmark pressure

UnisonAI contributes three local-engine pressure lanes:

- `teacher_exit_memory_ratchet`: correction permanence, negative feedback withholding, self-play non-reinforcement, teacher retirement, restart replay.
- `zero_parameter_corpus_law_eval`: fixed-item scorecard reproducibility, exact-count traceability, zero/low-parameter claim boundaries, verification suite coverage, same-machine comparison integrity.
- `react_discord_interface_scope`: ReAct follow-through, Discord scope lock, interface/engine separation, tool trace receipts, document ingest persistence, secret boundary.

## Files changed

- `C:\dev\local-model\dataset\unisonai_sources_2026-07-09.json`
- `C:\dev\local-model\scripts\model_card_benchmark_shapes.py`
- `C:\dev\local-model\scripts\run_source_mined_benchmark.py`
- `C:\dev\local-model\scripts\run_source_mined_backend_matrix.py`
- `C:\dev\local-model\scripts\run_m7_eval.py`
- `C:\dev\local-model\harness\source_mined_bench.py`
- `C:\dev\local-model\harness\unisonai_stateful_bench.py`
- `C:\dev\local-model\scripts\run_unisonai_stateful_benchmark.py`
- `C:\dev\local-model\tests\test_unisonai_stateful_bench.py`

## Validation

```powershell
python -m py_compile scripts/model_card_benchmark_shapes.py scripts/run_source_mined_benchmark.py scripts/run_source_mined_backend_matrix.py scripts/run_m7_eval.py harness/source_mined_bench.py
python scripts/model_card_benchmark_shapes.py --format validate
python scripts/run_source_mined_benchmark.py --category teacher_exit_memory_ratchet,zero_parameter_corpus_law_eval,react_discord_interface_scope --format validate
python scripts/run_m7_eval.py --source-mined --source-mined-category teacher_exit_memory_ratchet,zero_parameter_corpus_law_eval,react_discord_interface_scope --source-mined-providers dry --out C:/tmp/m7_unisonai_source_mined_dry.json
```

Observed:

- Source-mined case set: `26` cases, `23` categories, `164` unique metrics.
- UnisonAI deterministic lanes: `3/3` pass, `21` metrics.
- M7 dry artifact: `C:\tmp\m7_unisonai_source_mined_dry.json`.
- M7 dry row: pass rate `0.333`, quality `0.378`, latency `0 ms`, failures `none:3`.
- M7 witness gate: not required, passed.

## Live provider matrix

Command:

```powershell
python scripts/run_m7_eval.py --source-mined --source-mined-category teacher_exit_memory_ratchet,zero_parameter_corpus_law_eval,react_discord_interface_scope --source-mined-providers serve,ollama,codex,claude,opencode --frontier-model gpt-5.3-codex-spark --source-mined-endpoint-model gpt-5.3-codex-spark --source-mined-backend-timeout-seconds 150 --out C:/tmp/m7_unisonai_source_mined_provider_matrix.json
```

Artifact:

- `C:\tmp\m7_unisonai_source_mined_provider_matrix.json`

Observed rows:

- `serve` / `m7-source-mined-serve`: pass rate `1.0`, quality `0.748`, mean latency `43,329.667 ms`, failures `none:3`.
- `ollama` / `qwen2.5:7b`: pass rate `1.0`, quality `0.746`, mean latency `6,015 ms`, failures `none:3`.
- `codex` / `codex-plan`: pass rate `0.0`, quality `0.126`, mean latency `116,091 ms`, failures `timeout:2`, `low_task_focus:1`.
- `claude` / `claude-plan`: pass rate `0.0`, quality `0.0`, mean latency `2,926 ms`, failures `quota_or_rate_limit:3`.
- `opencode`: skipped because no configured endpoint backend exists for `plan`, `api`, `provider`, or `cloud` modes.

Summary:

- Operational rows: `3`.
- Skipped rows: `1`.
- Live rows: `4`.
- Flywheel `serve` minus Codex `codex`: pass-rate delta `+1.0`, quality delta `+0.622`, latency delta `-72,761.333 ms`.
- Witness gate: not required, passed.

## Stateful execution fixture

The UnisonAI lane now has a deterministic stateful fixture in addition to prompt-level provider scoring.

Command:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --state-root C:/tmp/unisonai_stateful_bench_state_20260709 --out C:/tmp/unisonai_stateful_benchmark_20260709.json --markdown-out C:/tmp/unisonai_stateful_benchmark_20260709.md
```

Artifacts:

- `C:\tmp\unisonai_stateful_benchmark_20260709.json`
- `C:\tmp\unisonai_stateful_benchmark_20260709.md`

Observed:

- Passed: `True`.
- Pass rate: `1.0`.
- Packet SHA-256: `4fcb9a6918322f078d17c715e9b9e87cdab1ad98797868556c5105d4198a7d8c`.
- Fixture schema: `unisonai.stateful-benchmark/v1`.

Stateful checks:

- `correction_permanence_score`
- `negative_ledger_enforcement`
- `persistent_memory_replay_score`
- `teacher_exit_evidence_score`
- `selfplay_nonreinforcement_score`
- `fixed_item_scorecard_reproducibility`
- `negative_result_preservation`
- `discord_scope_lock_score`
- `tool_trace_receipt_completeness`
- `secret_boundary_score`

## Provider-action fixture path

The stateful fixture can now be driven by a backend-style action response. Prose receives no credit; the provider must return JSON actions that mutate fixture state.

Validation:

```powershell
python -m pytest tests/test_unisonai_stateful_bench.py -q
```

Observed:

- `7 passed in 0.12s`

Scripted provider-action command:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --backend-actions-json C:/tmp/unisonai_stateful_backend_actions_20260709.json --state-root C:/tmp/unisonai_stateful_backend_state_20260709 --out C:/tmp/unisonai_stateful_backend_benchmark_20260709.json --markdown-out C:/tmp/unisonai_stateful_backend_benchmark_20260709.md
```

Artifacts:

- `C:\tmp\unisonai_stateful_backend_actions_20260709.json`
- `C:\tmp\unisonai_stateful_backend_benchmark_20260709.json`
- `C:\tmp\unisonai_stateful_backend_benchmark_20260709.md`

Observed:

- Passed: `True`.
- Pass rate: `1.0`.
- Packet SHA-256: `b7ec83974019af90149692db3fc96424531dc31b139e6dba3b64fe57b6117fef`.
- Fixture schema: `unisonai.stateful-backend-benchmark/v1`.
- Failure behavior: malformed or prose-only backend output is classified as `malformed_action_json` and receives pass rate `0.0`.

## Provider-selectable action matrix

The provider-action fixture now accepts provider selectors.

Dry provider proof:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry --state-root C:/tmp/unisonai_stateful_provider_matrix_state_20260709 --out C:/tmp/unisonai_stateful_provider_matrix_dry_20260709.json
```

Observed:

- Artifact: `C:\tmp\unisonai_stateful_provider_matrix_dry_20260709.json`
- Operational rows: `1`
- Mean pass rate: `1.0`

Live/current provider matrix:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry,serve,ollama,codex,claude,opencode --state-root C:/tmp/unisonai_stateful_provider_matrix_state_all_20260709 --out C:/tmp/unisonai_stateful_provider_matrix_all_20260709.json --backend-timeout-seconds 150
```

Observed:

- Artifact: `C:\tmp\unisonai_stateful_provider_matrix_all_20260709.json`
- Operational rows: `1`
- Mean pass rate across non-skipped rows: `0.2`
- `dry`: passed `True`, pass rate `1.0`, action count `8`.
- `serve` / `Qwen2.5-Coder-14B-Instruct (base, nf4)`: failed closed as `malformed_action_json`, action count `0`.
- `ollama/qwen2.5:7b`: failed closed as `malformed_action_json`, action count `0`.
- `codex/gpt-5.3-codex-spark`: failed closed as `malformed_action_json`, action count `0`.
- `claude`: failed as `provider_error`, `Credit balance is too low`.
- `opencode`: skipped, no configured endpoint backend for `plan,api,provider,cloud`.

## Repair-gated provider action matrix

The provider-action fixture now has an opt-in repair pass via `--repair-json`. The repair pass is accountable: it hashes the original malformed response and the repair response, records whether repair was attempted and succeeded, and still fails closed unless the repaired output is a non-empty executable action list.

Regression coverage:

```powershell
python -m pytest tests/test_unisonai_stateful_bench.py -q
```

Observed:

- `7 passed in 0.12s`
- Empty action arrays are rejected as `malformed_action_json`; they no longer count as successful repair.

Dry repair proof:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry --repair-json --state-root C:/tmp/unisonai_stateful_provider_matrix_repair_dry_state_20260709_v2 --out C:/tmp/unisonai_stateful_provider_matrix_repair_dry_20260709_v2.json
```

Observed:

- Artifact: `C:\tmp\unisonai_stateful_provider_matrix_repair_dry_20260709_v2.json`
- Operational rows: `1`
- Mean pass rate: `1.0`

Current repair-enabled provider matrix:

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry,serve,ollama,codex,claude,opencode --repair-json --state-root C:/tmp/unisonai_stateful_provider_matrix_repair_all_state_20260709_v2 --out C:/tmp/unisonai_stateful_provider_matrix_repair_all_20260709_v2.json --backend-timeout-seconds 150
```

Observed:

- Artifact: `C:\tmp\unisonai_stateful_provider_matrix_repair_all_20260709_v2.json`
- Rows: `6`
- Operational rows: `1`
- Skipped rows: `1`
- Live rows: `4`
- Mean pass rate across non-skipped rows: `0.2`
- Repair attempted rows: `3`
- Repair succeeded rows: `0`
- Repair success rate: `0.0`
- `dry`: passed `True`, pass rate `1.0`, action count `8`.
- `serve` / `Qwen2.5-Coder-14B-Instruct (base, nf4)`: repair attempted, repair failed, final failure `malformed_action_json`.
- `ollama/qwen2.5:7b`: repair attempted, repair failed, final failure `malformed_action_json`.
- `codex/gpt-5.3-codex-spark`: repair attempted, repair failed, final failure `malformed_action_json`.
- `claude`: failed as `provider_error`, `Credit balance is too low`.
- `opencode`: skipped, no configured endpoint backend for `plan,api,provider,cloud`.

Superseded artifact:

- `C:\tmp\unisonai_stateful_provider_matrix_repair_all_20260709.json` should not be used for conclusions; it came from the earlier permissive extraction path that accepted an empty action list during repair.

## Interpretation

The deterministic pass proves the benchmark case generation and oracle plumbing, not UnisonAI's claims. The dry M7 row intentionally shows that an echo-style backend is not enough to satisfy most UnisonAI-inspired gates.

The live matrix shows clear separation on the UnisonAI-inspired memory-ratchet, zero-parameter-claim-boundary, and Discord-interface-scope lanes. The active flywheel `serve` endpoint and local `ollama/qwen2.5:7b` row both passed all three cases. The Codex plan path for `gpt-5.3-codex-spark` failed this slice through timeouts and low task focus. Claude Code and OpenCode results remain endpoint/harness availability findings, not model-quality conclusions.

The stateful fixture closes the biggest measurement gap from the first UnisonAI integration pass. It now executes local state transitions and receipt generation for restart replay, negative-ledger withholding, fixed-item reproducibility, and Discord scope boundaries. It is still deterministic fixture evidence, not live model-agent execution evidence.

The provider-action path is the bridge between fixture evidence and live harness comparison. It proves the benchmark can score structured action execution and fail closed on prose-only output. The next live run should point `serve`, `ollama`, `codex`, Claude Code, and OpenCode at this action contract and record which providers can produce executable actions.

The current live action matrix is stricter than the earlier source-mined prompt matrix. The earlier prompt matrix rewarded providers for explaining the requirements. This action matrix only rewards executable JSON actions that mutate the fixture. Under that stricter contract, current live local and Codex rows failed closed rather than receiving partial credit for prose. That is a useful benchmark-hardening result, not a model superiority result.

The corrected repair matrix confirms that no current live row repairs into non-empty executable actions. That separates the present failure class more sharply: the harness can now measure output-contract failure, repair failure, provider quota failure, and missing OpenCode endpoint separately.

## Next promotion step

Promote from prompt-based repair to schema-constrained decoding or native tool-call output only if it preserves receipt accountability. The next live improvement should distinguish "model cannot plan correct actions" from "model can plan but violates output format" without awarding success to prose-only answers.
