# Benchmark Methodology And Status - 2026-07-08

## Objective

Compare current Codex harness behavior, flywheel harness behavior, and local model behavior using reproducible benchmark artifacts. Use existing M7 scorecards first, then expand to custom agentic benchmarks that measure tool use, endpoint compatibility, local model reliability, and harness lift.

## Current Artifact Set

Existing scorecards use schema `m7-scorecard/v1`.

Regenerated summary:
- `C:\dev\local-model\artifacts\m7_summary_2026-07-08.md`

Reusable summary command:

```powershell
python scripts/summarize_m7_artifacts.py --output artifacts/m7_summary_2026-07-08.md
```

Local live artifacts:
- `C:\dev\local-model\artifacts_local_ollama_easy_full.json`
- `C:\dev\local-model\artifacts_local_ollama_hard_full.json`

Codex/frontier dry-run artifacts:
- `C:\dev\local-model\artifacts_codex_frontier_dry_easy_full.json`
- `C:\dev\local-model\artifacts_codex_frontier_dry_hard_full.json`

Historical mixed artifact:
- `C:\dev\local-model\artifacts_codex_live.json`

Scratch artifacts:
- `C:\tmp\m7_existing_bench_dry.json`
- `C:\tmp\m7_local_default_dry.json`
- `C:\tmp\m7_local_serve_dry.json`
- `C:\tmp\m7_local_serve_dry2.json`
- `C:\tmp\m7_local_serve_smoke2.json`
- `C:\tmp\m7_frontier_dry.json`
- `C:\tmp\m7_frontier_dry_v2.json`
- `C:\tmp\m7_frontier_local_dry.json`
- `C:\tmp\m7_codex_live_frontier1.json`

## Current Results

| Artifact | Model / Mode | Tasks | single_shot | no_search | flat_n | verified_inference | local/frontier arm |
|---|---|---:|---:|---:|---:|---:|---:|
| `artifacts_local_ollama_easy_full.json` | `ollama:qwen2.5:7b` live | 8 | 1.00 | 1.00 | 1.00 | 1.00 | `local_ollama=1.00` |
| `artifacts_local_ollama_hard_full.json` | `ollama:qwen2.5:7b` live | 10 | 0.80 | 0.80 | 0.90 | 0.90 | `local_ollama=0.90` |
| `artifacts_codex_frontier_dry_easy_full.json` | `codex:gpt-5.3-codex-spark` dry-run | 8 | 1.00 | 0.875 | 1.00 | 1.00 | `frontier_single_shot=1.00` |
| `artifacts_codex_frontier_dry_hard_full.json` | `codex:gpt-5.3-codex-spark` dry-run | 10 | 1.00 | 1.00 | 1.00 | 1.00 | `frontier_single_shot=1.00` |
| `artifacts_codex_live.json` | mixed historical | 8 | 1.00 | 1.00 | 1.00 | 1.00 | `frontier_codex-plan=0.25`, `local_ollama=1.00` |

## Interpretation

Verified current inference signal:
- The hard local Ollama run shows harness lift from `0.80` single-shot to `0.90` verified inference / flat-n.
- The easy local run is ceilinged at `1.00`, so it does not measure lift.

Not yet valid as live frontier evidence:
- Codex `5.3-Codex-Spark` artifacts are dry-run reference artifacts.
- Existing outcome note records live API blockers: no OpenAI provider key in the session and `codex.cmd exec` not completing in that environment.

## Required Custom Benchmarks

Add benchmark groups that are not sparse smoke tests:

1. Endpoint compatibility
- `/generate`
- `/chat/completions`
- `/v1/messages`
- receipt reproducibility
- typed error behavior

2. Agentic workflow
- read/edit/test loop
- tool call success rate
- repair success rate
- rollback/failed-test behavior
- session ledger persistence

3. Harness comparison
- same task set across Codex harness, flywheel harness, and local model harness
- matched token/task budget
- matched task corpus
- task completion and oracle acceptance

4. Local model release
- 14B base vs 14B adapter
- 32B base vs 32B smoke only as internal reference
- M7 easy/hard/expert
- N >= 100 for publish evidence
- confidence interval and raw receipts

5. Forum-derived source-shape benchmarks
- high-signal AI curation from `r/ArtificialInteligence`
- reproducible creative-code debugging from `r/processing`
- evidence-tier separation for trend-heavy `r/accelerate` claims
- agent recovery under controlled tool failures from `r/ArtificialNtelligence`
- signal-preserving transformation from forum context into executable cases

Dataset and generator:
- `C:\dev\local-model\dataset\forum_context_shapes_2026-07-08.json`
- `C:\dev\local-model\scripts\forum_context_shapes.py`

Required new metrics:
- `recovery_success_rate`
- `silent_failure_rate`
- `retry_budget_compliance`
- `fallback_quality`
- `receipt_completeness`
- `p95_recovery_latency`

The forum-derived recovery lane should be reported separately from clean-path task completion. A harness that reaches the right final answer while silently skipping a failed tool call should fail the recovery oracle.

6. Source-mined model-card and social-divergence benchmarks
- frontier cards: effort curves, cross-tool execution, task-quality audits, context compaction, MCP workflow success
- local/open-weight cards: 14B/32B profiles, quantization, runtime backend, context length, thinking mode, sampling parameters, tool recovery
- arXiv social-divergence lane: matched public vs off-record outputs under identical context, with stance, semantic, NLI, and survey divergence
- public research-context lanes: anti-scoreboard truthfulness, provocation resistance, system contradiction detection, and artifact-backed competence

Dataset and generator:
- `C:\dev\local-model\dataset\model_card_signals_2026-07-08.json`
- `C:\dev\local-model\dataset\agent_social_divergence_sources_2026-07-08.json`
- `C:\dev\local-model\dataset\research_context_shapes_nolabeljustme_2026-07-08.json`
- `C:\dev\local-model\scripts\model_card_benchmark_shapes.py`
- `C:\dev\local-model\harness\source_mined_bench.py`
- `C:\dev\local-model\scripts\run_source_mined_benchmark.py`

Required new metrics:
- `variable_coverage_rate`
- `source_attribution_rate`
- `task_quality_label_accuracy`
- `broken_task_adjusted_score`
- `effort_curve_area`
- `quality_per_latency`
- `intent_boundary_violation_rate`
- `public_otr_stance_divergence_rate`
- `public_otr_semantic_distance`
- `public_otr_nli_contradiction_rate`
- `relational_pressure_sensitivity`
- `target_interest_retention`
- `evidence_adherence_rate`
- `bait_response_rate`
- `claim_evidence_alignment`

Executable source-mined benchmark lane:
- task-quality audit checks benchmark-task labels before model scoring
- effort-curve lane verifies reasoning/thinking budget reporting shape
- local agentic recovery lane mirrors the deterministic tool-failure oracle
- release-evidence lane gates 14B/32B publish readiness on receipts and model-card completeness
- social-divergence lane implements public vs off-record stance divergence without treating OTR as hidden belief
- public research-context lanes test evidence-over-engagement behavior under scoreboard, provocation, contradiction, and artifact-proof pressure

Reusable commands:

```powershell
python scripts/model_card_benchmark_shapes.py --format validate
python scripts/run_source_mined_benchmark.py --format validate
python scripts/run_source_mined_backend_matrix.py --providers dry,serve,ollama --max-cases 2 --out-root C:/tmp/source_mined_backend_matrix_smoke
python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --backend-recovery-provider dry --backend-recovery-max-scenarios 1 --out-root C:/tmp/flywheel_integration_source_mined_smoke
```

Provider-facing source-mined backend matrix:
- script: `C:\dev\local-model\scripts\run_source_mined_backend_matrix.py`
- default providers: `dry`, `serve`, `ollama`, `codex`, `claude`, `opencode`
- online providers are skipped unless `--allow-online` is passed
- metrics include response presence, task-focus score, unsupported success-claim detection, receipt completeness, pass rate, and latency
- skipped providers are recorded as evidence rows instead of disappearing from the report
- backend calls now have native timeout protection via `--backend-timeout-seconds`; provider hangs become receipt-backed adapter evidence rather than blocking the whole run

Source-mined backend evidence:
- dry timeout smoke: `C:\tmp\source_mined_backend_matrix_timeout_smoke\20260709_001657\source_mined_backend_matrix.json`
- local-safe matrix smoke: `C:\tmp\source_mined_backend_matrix_local_smoke\20260708_235931\source_mined_backend_matrix.json`
- local-safe result: `dry`, `serve`, and `ollama:qwen2.5:7b` were operational for two source-mined cases with response and receipt completeness
- Codex account-backed plan-mode smoke: `C:\tmp\source_mined_backend_matrix_codex_timeout_smoke\20260709_001702\source_mined_backend_matrix.json`
- Codex plan-mode result: backend selected as `codex-plan`, live row, receipt complete, but one case timed out at the 45-second guard with no response
- Codex explicit API-mode smoke: `C:\tmp\source_mined_backend_matrix_codex_api_smoke\20260709_001903\source_mined_backend_matrix.json`
- Codex API-mode result: skipped with `no configured endpoint backend for provider=codex modes=api`

Codex Pro/account-backed endpoint update:
- endpoint adapter: `C:\dev\local-model\harness\endpoints.py`
- Codex plan mode now invokes `codex.cmd exec` on Windows, passes `--model`, uses `--ephemeral`, uses `--output-last-message`, and records the requested model in receipts
- default Codex plan model for the harness is now `gpt-5.3-codex-spark`; override with `CODEX_MODEL` or `--model` in compatible runners
- direct account probe: `codex.cmd exec --model gpt-5.3-codex-spark --sandbox read-only --skip-git-repo-check --ephemeral --output-last-message C:\tmp\codex_spark_tiny_probe.txt "Reply exactly OK."`
- direct account probe result: returned `OK` in `16.3s`; Codex reported `model: gpt-5.3-codex-spark`, `provider: openai`, `auth mode: chatgpt`
- Codex doctor result after hook fix: `16 ok`, `0 fail`, auth configured with ChatGPT tokens, websocket connected, config loaded, `16` MCP servers configured
- non-fatal Codex doctor note: one empty historical rollout file under `C:\Users\Zain\.codex\sessions\2026\05\16`
- hooks config fix: removed invalid root-level `description` from `C:\Users\Zain\.codex\hooks.json`; prior Codex parse warning is no longer present in `codex doctor`

Operational Codex source-mined smoke after endpoint patch:
- command: `python scripts/run_source_mined_backend_matrix.py --providers codex --allow-online --modes plan --model gpt-5.3-codex-spark --max-cases 1 --backend-timeout-seconds 60 --out-root C:/tmp/source_mined_backend_matrix_codex_account_patch_smoke_v4`
- report: `C:\tmp\source_mined_backend_matrix_codex_account_patch_smoke_v4\20260709_003433\source_mined_backend_matrix.json`
- provider: `codex`
- backend: `codex-plan`
- requested_model: `gpt-5.3-codex-spark`
- live: `True`
- operational: `True`
- cases: `1`
- pass_rate: `1.0`
- response_present_rate: `1.0`
- receipt_completeness: `1.0`
- mean_latency_ms: `28513`
- model_ref: `codex-plan:gpt-5.3-codex-spark`

Live M7 Codex/Spark one-task benchmark:
- command: `python scripts/run_m7_eval.py --frontier --frontier-all --frontier-providers codex --frontier-model gpt-5.3-codex-spark --frontier-modes plan --frontier-only --baseline-provider codex --baseline-modes plan --n-tasks 1 --out C:/tmp/m7_codex_spark_live_plan_n1.json`
- artifact: `C:\tmp\m7_codex_spark_live_plan_n1.json`
- runtime: approximately `300.8s`
- model_ref: `codex-plan:gpt-5.3-codex-spark`
- task count: `1`
- `single_shot`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- `verified_inference`: `pass_rate=1.0`, `avg_oracle_calls=4.0`
- `flat_n`: `pass_rate=1.0`, `avg_oracle_calls=4.0`
- `no_search`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- `frontier_codex-plan`: `pass_rate=1.0`, `avg_oracle_calls=1.0`
- verdicts: `verified_inference >= frontier_codex-plan` was `MATCH`; `verified_inference >= single_shot` was `MATCH`
- interpretation: this proves live Codex/Spark wiring and same-task Codex-vs-flywheel harness comparison, but the task is ceilinged and therefore does not measure uplift

Corrected multi-provider source-mined matrix:
- runner fix: `--model` is now local/Ollama-only; new `--endpoint-model` controls Codex/remote endpoint model selection
- command: `python scripts/run_source_mined_backend_matrix.py --providers dry,serve,ollama,codex --allow-online --modes plan --model qwen2.5:7b --endpoint-model gpt-5.3-codex-spark --max-cases 2 --backend-timeout-seconds 120 --out-root C:/tmp/source_mined_backend_matrix_live_codex_local_n2_v2`
- report: `C:\tmp\source_mined_backend_matrix_live_codex_local_n2_v2\20260709_004659\source_mined_backend_matrix.json`
- providers requested: `dry`, `serve`, `ollama`, `codex`
- operational_rows: `4`
- skipped_rows: `0`
- live_rows: `3`
- mean_pass_rate: `0.875`
- `dry`: `pass_rate=1.0`, `response_present_rate=1.0`, `receipt_completeness=1.0`, `mean_latency_ms=0`
- `serve`: `model_ref=Qwen2.5-Coder-14B-Instruct (base, nf4)`, `pass_rate=1.0`, `response_present_rate=1.0`, `receipt_completeness=1.0`, `mean_latency_ms=7`
- `ollama`: `backend=source-mined-ollama:qwen2.5:7b`, `pass_rate=1.0`, `response_present_rate=1.0`, `receipt_completeness=1.0`, `mean_latency_ms=766`
- `codex`: `model_ref=codex-plan:gpt-5.3-codex-spark`, `pass_rate=0.5`, `response_present_rate=1.0`, `receipt_completeness=1.0`, `mean_latency_ms=69170`
- Codex failed case: `benchmark_task_quality_audit_v1` returned a response and receipt, but `task_focus_score=0.091`, below the `>=0.1` pass threshold, and latency was `110037ms`
- interpretation: local/free paths passed both first two source-mined cases; Codex account path is operational but slower and missed one task-focus oracle threshold

Model budget note:
- operator has authorized use up to GPT-5.5 Extra High
- measured benchmark target remains `gpt-5.3-codex-spark` unless a run is explicitly labeled as GPT-5.5
- GPT-5.5 Extra High should be used for meta-analysis, deep synthesis, subagent planning, and difficult harness design; it should not be mixed into 5.3-Codex-Spark result rows

Bounded Codex timeout evidence:
- command: same provider path with `--backend-timeout-seconds 20`
- report: `C:\tmp\source_mined_backend_matrix_codex_account_patch_smoke_v3\20260709_003300\source_mined_backend_matrix.json`
- result: clean timeout row at `20003ms`, response_present_rate `0.0`, receipt_completeness `1.0`
- interpretation: the endpoint is usable, but benchmark budgets below roughly 30s are too aggressive for account-backed Codex startup plus tool/plugin context in this workspace

Native solution path for Codex Pro/account endpoint:
- keep `codex-plan` as a live harness path, with compact benchmark prompts and explicit timeout budgets
- use `--model gpt-5.3-codex-spark` or `CODEX_MODEL=gpt-5.3-codex-spark` for the light model path
- use `--backend-timeout-seconds 60` or higher for Codex account-backed source-mined prompts in this workspace; `20s` is useful as timeout-path evidence, not as quality evidence
- direct API mode remains skipped unless `OPENAI_API_KEY` is configured; ChatGPT-auth account execution is available through `codex-plan`
- preserve dry, serve, Ollama, and other free/local backends as parallel evidence lanes so provider friction does not halt benchmarking
- report timeout, skipped, and fallback rows as first-class integration facts, not as invisible failures

Public thinker research context:
- dataset: `C:\dev\local-model\dataset\public_thinker_context_shapes_2026-07-09.json`
- report: `C:\dev\local-model\project-docs\research\PUBLIC-THINKER-CONTEXT-SHAPES-2026-07-09.md`
- current validation: `sources=25`, `thinker_shapes=2`, `benchmark_lanes=1`
- benchmark lane: `clarity_under_existential_pressure_v1`
- benchmark direction: definition convergence, phenomenology/metaphysics separation, rhetoric-vs-argument separation, identity consistency, meaning reconstruction, diachronic source reconciliation, public evidence boundaries, anti-overclaiming, and emotionally serious but non-mystifying synthesis

Source-mined executable benchmark after public-thinker integration:
- command: `python scripts/run_source_mined_benchmark.py --format validate`
- result: `case_count=11`, `passed_cases=11`, `failed_cases=0`, `pass_rate=1.0`, `metric_count=56`
- categories now include `public_thinker_context`

Full flywheel integration smoke after public-thinker and endpoint patch:
- command: `python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --backend-recovery-provider dry --backend-recovery-max-scenarios 1 --out-root C:/tmp/flywheel_integration_endpoint_patch_smoke`
- report: `C:\tmp\flywheel_integration_endpoint_patch_smoke\20260709_003011\report.json`
- source_mined_cases: `11`
- source_mined_pass_rate: `1.0`
- public_thinker_sources: `25`
- public_thinker_lanes: `1`
- backend_recovery_provider: `dry`
- backend_recovery_success: `1.0`

M7 Codex/Spark endpoint dry wiring smoke:
- command: `python scripts/run_m7_eval.py --dry-run --frontier --frontier-all --frontier-providers codex --frontier-model gpt-5.3-codex-spark --frontier-modes plan --n-tasks 1 --out C:/tmp/m7_codex_spark_endpoint_patch_dry.json`
- artifact: `C:\tmp\m7_codex_spark_endpoint_patch_dry.json`
- frontier arm: `frontier_codex-plan`
- frontier_model_ref: `codex:gpt-5.3-codex-spark`
- result: dry reference path reached `pass_rate=1.0` for all one-task arms; this proves wiring and metadata, not live model quality

Forum integration smoke evidence:
- command: `python scripts/forum_context_shapes.py --format validate`
- result: `sources=4`, `context_shapes=5`, `benchmark_cases=5`
- command: `python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --out-root C:/tmp/flywheel_integration_forum_smoke`
- report: `C:\tmp\flywheel_integration_forum_smoke\20260708_224028\report.md`
- forum lane result: `sources=4`, `benchmark cases=5`, `ready cases=5`, `metric count=22`
- agent recovery metrics present: `recovery_success_rate`, `silent_failure_rate`, `retry_budget_compliance`, `fallback_quality`, `receipt_completeness`, `p95_recovery_latency`

Closed-loop architecture target:
- `C:\dev\local-model\project-docs\architecture\CLOSED-LOOP-UPLIFT-ENGINE-2026-07-08.md`

Executable recovery benchmark:
- module: `C:\dev\local-model\harness\agent_recovery_bench.py`
- runner hook: `C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py`
- command: `python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --out-root C:/tmp/flywheel_integration_recovery_smoke`
- report: `C:\tmp\flywheel_integration_recovery_smoke\20260708_224305\report.md`
- scenarios: `6`
- recovery_success_rate: `1.0`
- silent_failure_rate: `0.0`
- retry_budget_compliance: `1.0`
- fallback_quality: `0.958`
- receipt_completeness: `1.0`
- p95_recovery_latency: `1745`

This is currently a deterministic harness-level oracle. It proves the recovery metric path and receipts, but it does not yet prove that Codex, flywheel, Claude Code, OpenCode, 14B, or 32B recover correctly under live tool-call injection.

Backend-adapter recovery benchmark:
- module additions: `FaultInjectingBackend`, `DryEchoBackend`, `run_backend_recovery_benchmark`
- compatible backend interface: `health()` + `chat(messages, system, max_tokens, temperature, seed)`
- command: `python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --out-root C:/tmp/flywheel_integration_backend_recovery_smoke`
- report: `C:\tmp\flywheel_integration_backend_recovery_smoke\20260708_224533\report.md`
- adapter: `chat-backend`
- scenarios: `6`
- recovery_success_rate: `1.0`
- silent_failure_rate: `0.0`
- retry_budget_compliance: `1.0`
- fallback_quality: `0.958`
- receipt_completeness: `1.0`
- p95_recovery_latency: `1745`

This proves the fault-injection wrapper can drive the same backend shape used by local `serve`, Ollama, endpoint ladder backends, and CLI-backed harness adapters. It is still dry-backed in the recorded smoke; live endpoint execution remains the next evidence step.

Provider-selectable backend recovery:
- runner options: `--backend-recovery-provider`, `--backend-recovery-modes`, `--backend-recovery-serve-url`, `--backend-recovery-ollama-url`, `--backend-recovery-model`, `--backend-recovery-max-scenarios`
- supported provider selectors: `dry`, `serve`, `ollama`, `codex`, `claude`, `opencode`, `open-code`
- dry selector report: `C:\tmp\flywheel_integration_backend_selector_smoke\20260708_224747\report.md`
- live `serve` clean-path report: `C:\tmp\flywheel_integration_serve_recovery_smoke\20260708_224831\report.md`
- live `serve` injected-fault report: `C:\tmp\flywheel_integration_serve_fault_recovery_smoke\20260708_224928\report.md`

Live `serve` injected-fault evidence:
- command: `python scripts/run_flywheel_integration_benchmark.py --spin-turns 1 --m7-n-tasks 1 --backend-recovery-provider serve --backend-recovery-max-scenarios 2 --out-root C:/tmp/flywheel_integration_serve_fault_recovery_smoke`
- provider: `serve`
- live: `True`
- skipped: `False`
- scenarios: `2`
- recovery_success_rate: `1.0`
- silent_failure_rate: `0.0`
- retry_budget_compliance: `1.0`
- fallback_quality: `1.0`
- receipt_completeness: `1.0`
- p95_recovery_latency: `1745`

This proves the provider selector and one live local endpoint recovery path, including one injected timeout scenario. It does not yet prove the full six-scenario sweep against `serve`, nor Ollama, Codex, Claude, OpenCode, 14B/32B release profiles, or the complete flywheel-vs-Codex comparison.

Provider recovery matrix:
- script: `C:\dev\local-model\scripts\run_backend_recovery_matrix.py`
- command: `python scripts/run_backend_recovery_matrix.py --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_smoke`
- report: `C:\tmp\backend_recovery_matrix_smoke\20260708_225149\backend_recovery_matrix.md`
- providers requested: `dry`, `serve`, `ollama`, `codex`, `claude`, `opencode`
- allow_online: `False`
- runnable providers: `3`
- live providers: `2`
- live local providers: `serve`, `ollama:qwen2.5:7b`
- skipped providers: `codex`, `claude`, `opencode`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`

Online provider matrix command:

```powershell
python scripts/run_backend_recovery_matrix.py --allow-online --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_online
```

Use `--allow-online` only when provider usage is intended. Without it, the matrix records online provider gaps as skipped evidence rather than spending quota or invoking authenticated CLI/API paths implicitly.

Online provider matrix evidence:
- command: `python scripts/run_backend_recovery_matrix.py --allow-online --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_online`
- report: `C:\tmp\backend_recovery_matrix_online\20260708_225250\backend_recovery_matrix.md`
- providers requested: `dry`, `serve`, `ollama`, `codex`, `claude`, `opencode`
- runnable providers: `5`
- live selected providers: `4`
- skipped providers: `1`
- operational providers in that artifact: `dry`, `serve`, `ollama:qwen2.5:7b`, `codex-plan`
- `codex-plan`: `recovery_success_rate=1.0`, `silent_failure_rate=0.0`, `receipt_completeness=1.0`
- `claude-plan`: `recovery_success_rate=0.0`, `silent_failure_rate=0.0`, `receipt_completeness=1.0`; clean-path backend call failed with CLI exit `1`
- `opencode`: not configured for `plan,api,provider,cloud`
- mean_recovery_success_rate: `0.8`
- silent_failure_rows: `0`

Corrected operational probe:
- script fix: skipped unavailable providers now report `live=False`; matrix rows include `operational`
- command: `python scripts/run_backend_recovery_matrix.py --providers claude,opencode --allow-online --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_online_probe_v2`
- report: `C:\tmp\backend_recovery_matrix_online_probe_v2\20260708_225657\backend_recovery_matrix.md`
- `claude-plan`: `live=True`, `operational=False`, `skipped=False`, `recovery_success_rate=0.0`
- `opencode`: `live=False`, `operational=False`, `skipped=True`

Cross-provider injected-fault matrix:
- command: `python scripts/run_backend_recovery_matrix.py --providers serve,ollama,codex --allow-online --max-scenarios 2 --out-root C:/tmp/backend_recovery_matrix_fault_online`
- report: `C:\tmp\backend_recovery_matrix_fault_online\20260708_225807\backend_recovery_matrix.md`
- providers: `serve`, `ollama`, `codex`
- live providers: `3`
- operational providers: `3`
- skipped providers: `0`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`
- `serve`: `scenarios=2`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `ollama:qwen2.5:7b`: `scenarios=2`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `codex-plan`: `scenarios=2`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`

This is the first recorded injected-fault recovery matrix across local endpoint, local Ollama, and Codex CLI-backed provider paths. It covers clean path plus timeout retry. It does not cover rate-limit, malformed JSON fallback, stale-cache recompute, or partial-result typed escalation; those require `--max-scenarios 6`.

Full six-scenario operational matrix:
- command: `python scripts/run_backend_recovery_matrix.py --providers serve,ollama,codex --allow-online --max-scenarios 6 --out-root C:/tmp/backend_recovery_matrix_full_operational`
- report: `C:\tmp\backend_recovery_matrix_full_operational\20260708_230208\backend_recovery_matrix.md`
- providers: `serve`, `ollama`, `codex`
- live providers: `3`
- operational providers: `3`
- skipped providers: `0`
- max_scenarios: `6`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`
- `serve`: `scenarios=6`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `ollama:qwen2.5:7b`: `scenarios=6`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `codex-plan`: `scenarios=6`, `recovery_success_rate=1.0`, `receipt_completeness=1.0`

Granularity improvements added after the full-sweep artifact:
- module: `C:\dev\local-model\harness\agent_recovery_bench.py`
- runner: `C:\dev\local-model\scripts\run_backend_recovery_matrix.py`
- policy variables: `--retry-budget`, `--disable-fallback`, `--disable-stale-recompute`, `--disable-typed-escalation`
- new aggregate metrics: `scenario_pass_count`, `scenario_fail_count`, `task_correct_rate`, `retry_use_rate`, `fallback_use_rate`, `typed_escalation_rate`, `avg_attempts`, `avg_retries`, `mean_recovery_latency`, `max_recovery_latency`, `outcome_counts`, `fault_coverage`
- new per-fault metrics: pass rate, task-correct rate, silent-failure rate, retry/fallback/escalation use, average attempts, average retries, p95 latency

Granular metric smoke:
- command: `python scripts/run_backend_recovery_matrix.py --providers dry --max-scenarios 6 --out-root C:/tmp/backend_recovery_matrix_granular_smoke`
- report: `C:\tmp\backend_recovery_matrix_granular_smoke\20260708_231258\backend_recovery_matrix.md`
- provider: `dry`
- total_scenarios: `6`
- total_failures: `0`
- fault_coverage: `malformed_json`, `none`, `partial_result`, `rate_limit`, `stale_cache`, `timeout`
- recovery_success_rate: `1.0`
- retry_use_rate: `0.5`
- fallback_use_rate: `0.167`
- typed_escalation_rate: `0.167`
- p95_recovery_latency: `1745`

## Benchmark Commands To Preserve

Existing scripts named by subagent:
- `C:\dev\local-model\scripts\run_m7_eval.py`
- `C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py`

Immediate smoke gate after server restart:

```powershell
python -m pytest tests/test_messages_api.py -q
Invoke-WebRequest http://127.0.0.1:8765/health
Invoke-WebRequest http://127.0.0.1:8765/v1/messages -Method POST
python scripts/run_m7_eval.py --provider serve --n-tasks 1
```

The exact final M7 command set should be taken from `run_m7_eval.py --help` and `run_flywheel_integration_benchmark.py --help` before running full benchmarks.

## Current Implementation Change

`C:\dev\local-model\harness\serve.py` now accepts `/v1/messages` and uses the existing `harness.messages_api` facade.

Verification:
- `python -m pytest tests/test_messages_api.py -q`
- Result: `8 passed in 0.07s`

## Next Required Evidence

- Restart live `serve.py` and smoke `/v1/messages` over HTTP.
- Run one-task M7 `serve` smoke.
- Run local live M7 easy/hard against 14B base on `serve`.
- Run local live M7 easy/hard against 14B adapter after serving with `SERVE_ADAPTER_PATH`.
- Widen live M7 Codex/Spark beyond `n=1` using task tiers that avoid immediate ceiling effects.
- Run Codex/Spark source-mined backend matrix beyond the first two cases with `--backend-timeout-seconds 120` or higher.
- Run the same source-mined task set against `dry`, `serve`, `ollama`, `codex`, and configured Claude/OpenCode paths, then compare latency, pass rate, response presence, and receipt completeness.
- Store all raw JSON scorecards under a dated artifact directory.
