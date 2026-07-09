# Closed-Loop Uplift Engine - 2026-07-08

## North Star

Build a complete, shareable engine for continuous uplift across local models, agent harnesses, routers, tools, benchmarks, compression, packaging, and release evidence.

The system target is not a single model or script. The target is a closed loop:

```text
context intake
  -> source-shape curation
  -> benchmark generation
  -> harness execution
  -> routing and tool-use measurement
  -> failure analysis
  -> data/model/tool improvement
  -> compression and packaging
  -> release evidence
  -> redistributed capability
  -> new context intake
```

## Required Integration Surface

The final system should plug in, at minimum:

- Codex harness
- flywheel harness
- Claude Code harness path
- OpenCode harness path
- local model endpoint server
- 14B and 32B model release tracks
- mneme memory substrate
- relay transport/integration layer
- plexus orchestration layer
- index workspace map
- forum routing and gradable trajectory intake
- gather, crucible, telos, and related workspace tools where present
- benchmark artifacts, scorecards, receipts, and release reports

## Uplift Domains

The loop must improve four domains at once:

- Model capability: task quality, reasoning reliability, instruction following, tool use, coding, recovery, and compression efficiency.
- Harness capability: reproducible execution, endpoint compatibility, agentic workflow coverage, failure injection, metrics, and artifact hygiene.
- Router capability: correct lane selection, tool choice, escalation, cost/latency control, and robustness under ambiguous tasks.
- Package capability: smaller deployable models, executable harnesses, stable configs, docs, examples, checksums, and release criteria.

## Benchmark Philosophy

The harness should exceed user metrics by measuring what users actually experience:

- task completion
- answer quality
- latency
- cost and resource use
- tool-call success
- recovery from tool failure
- routing accuracy
- reproducibility
- user-visible usefulness
- artifact traceability
- installability and shareability

Sparse smoke tests are only gates. The main benchmark corpus should include real agentic workflows, controlled failure cases, forum-derived source-shape tasks, local endpoint tests, and release-grade model comparisons.

## Current New Loop Input

The Reddit forum source-shape pass added one input lane:

- Dataset: `C:\dev\local-model\dataset\forum_context_shapes_2026-07-08.json`
- Generator: `C:\dev\local-model\scripts\forum_context_shapes.py`
- Integration runner hook: `C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py`
- Smoke artifact: `C:\tmp\flywheel_integration_forum_smoke\20260708_224028\report.md`

The new lane contributes:

- source-quality curation cases
- creative-code grounded debugging cases
- agent recovery under controlled tool failures
- trend evidence-gating cases
- signal-preserving transformation cases

## Current Executable Recovery Primitive

The first executable recovery primitive now exists:

- Module: `C:\dev\local-model\harness\agent_recovery_bench.py`
- Runner integration: `C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py`
- Smoke artifact: `C:\tmp\flywheel_integration_recovery_smoke\20260708_224305\report.md`

Measured smoke result:

- scenarios: `6`
- recovery_success_rate: `1.0`
- silent_failure_rate: `0.0`
- retry_budget_compliance: `1.0`
- fallback_quality: `0.958`
- receipt_completeness: `1.0`
- p95_recovery_latency: `1745`

This primitive is deterministic and harness-level. It measures timeout retry, rate-limit retry, malformed-response fallback, stale-cache recompute, partial-result typed escalation, and clean-path completion before live model variability is introduced.

The second recovery primitive now wraps actual chat-backend interfaces:

- Wrapper: `FaultInjectingBackend`
- Dry backend: `DryEchoBackend`
- Runner section: `Backend-adapter recovery benchmark`
- Smoke artifact: `C:\tmp\flywheel_integration_backend_recovery_smoke\20260708_224533\report.md`

Measured backend-adapter smoke result:

- adapter: `chat-backend`
- scenarios: `6`
- recovery_success_rate: `1.0`
- silent_failure_rate: `0.0`
- retry_budget_compliance: `1.0`
- fallback_quality: `0.958`
- receipt_completeness: `1.0`
- p95_recovery_latency: `1745`

This wrapper can accept the same `health()` and `chat()` shape used by local `serve`, Ollama, OpenAI-compatible endpoint backends, Anthropic-compatible endpoint backends, Gemini backends, and CLI-backed Codex/Claude/OpenCode adapters.

The runner now exposes the backend selector:

```powershell
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider dry
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider serve --backend-recovery-max-scenarios 2
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider ollama --backend-recovery-model <model>
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider codex --backend-recovery-modes plan,api
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider claude --backend-recovery-modes plan,api
python C:\dev\local-model\scripts\run_flywheel_integration_benchmark.py --backend-recovery-provider opencode --backend-recovery-modes plan
```

Verified selector evidence:

- Dry selector smoke: `C:\tmp\flywheel_integration_backend_selector_smoke\20260708_224747\report.md`
- Live `serve` clean-path smoke: `C:\tmp\flywheel_integration_serve_recovery_smoke\20260708_224831\report.md`
- Live `serve` injected-fault smoke: `C:\tmp\flywheel_integration_serve_fault_recovery_smoke\20260708_224928\report.md`
- Provider matrix smoke: `C:\tmp\backend_recovery_matrix_smoke\20260708_225149\backend_recovery_matrix.md`
- Online provider matrix: `C:\tmp\backend_recovery_matrix_online\20260708_225250\backend_recovery_matrix.md`
- Corrected Claude/OpenCode operational probe: `C:\tmp\backend_recovery_matrix_online_probe_v2\20260708_225657\backend_recovery_matrix.md`
- Online injected-fault matrix for operational providers: `C:\tmp\backend_recovery_matrix_fault_online\20260708_225807\backend_recovery_matrix.md`
- Full six-scenario operational matrix before granular columns: `C:\tmp\backend_recovery_matrix_full_operational\20260708_230208\backend_recovery_matrix.md`
- Granular metric smoke: `C:\tmp\backend_recovery_matrix_granular_smoke\20260708_231258\backend_recovery_matrix.md`

Live `serve` injected-fault smoke result:

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

Provider matrix smoke result:

- providers: `6`
- runnable: `3`
- live: `2`
- skipped: `3`
- live local providers: `serve`, `ollama:qwen2.5:7b`
- online providers skipped by default: `codex`, `claude`, `opencode`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`

Matrix runner:

```powershell
python C:\dev\local-model\scripts\run_backend_recovery_matrix.py --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_smoke
python C:\dev\local-model\scripts\run_backend_recovery_matrix.py --allow-online --max-scenarios 1 --out-root C:/tmp/backend_recovery_matrix_online
```

Online matrix result:

- providers: `6`
- runnable: `5`
- live selected backends: `serve`, `ollama:qwen2.5:7b`, `codex-plan`, `claude-plan`
- operational clean-path providers in that artifact: `dry`, `serve`, `ollama:qwen2.5:7b`, `codex-plan`
- `claude-plan` selected but failed clean-path execution with CLI exit `1`
- `opencode` was not configured
- mean_recovery_success_rate: `0.8`
- silent_failure_rows: `0`

The follow-up corrected probe adds an explicit `operational` column and fixes skipped-provider live reporting:

- `claude-plan`: `live=True`, `operational=False`, `recovery_success_rate=0.0`
- `opencode`: `live=False`, `operational=False`, `skipped=True`

Online injected-fault matrix result:

- providers: `serve`, `ollama`, `codex`
- max_scenarios: `2`
- live: `3`
- operational: `3`
- skipped: `0`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`
- `serve`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `ollama:qwen2.5:7b`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `codex-plan`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`

This is the first recorded cross-provider injected-fault recovery evidence. It covers clean path plus timeout retry for the currently operational provider set.

Full six-scenario operational matrix result:

- providers: `serve`, `ollama`, `codex`
- max_scenarios: `6`
- live: `3`
- operational: `3`
- skipped: `0`
- mean_recovery_success_rate: `1.0`
- silent_failure_rows: `0`
- `serve`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `ollama:qwen2.5:7b`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`
- `codex-plan`: `recovery_success_rate=1.0`, `receipt_completeness=1.0`

Granular metric surface now includes:

- policy variables: `retry_budget`, `fallback_enabled`, `stale_recompute_enabled`, `typed_escalation_enabled`
- aggregate variables: `scenario_pass_count`, `scenario_fail_count`, `task_correct_rate`, `retry_use_rate`, `fallback_use_rate`, `typed_escalation_rate`, `avg_attempts`, `avg_retries`, `mean_recovery_latency`, `max_recovery_latency`
- categorical variables: `outcome_counts`, `fault_coverage`
- per-fault variables: pass rate, task-correct rate, silent-failure rate, retry/fallback/escalation use, average attempts, average retries, and p95 latency

Granular smoke result:

- provider: `dry`
- max_scenarios: `6`
- fault_coverage: `malformed_json`, `none`, `partial_result`, `rate_limit`, `stale_cache`, `timeout`
- total_scenarios: `6`
- total_failures: `0`
- recovery_success_rate: `1.0`
- retry_use_rate: `0.5`
- fallback_use_rate: `0.167`
- typed_escalation_rate: `0.167`
- p95_recovery_latency: `1745`

## Immediate Architecture Gaps

- Full `index` scan of `C:\dev` failed on a non-UTF-8 decode error; current confirmed index evidence is scoped to `C:\dev\local-model`.
- Forum-derived cases are integrated as benchmark-case artifacts, but not yet executed as live model prompts against Codex, flywheel, Claude Code, OpenCode, 14B, or 32B.
- The agent-recovery lane now has a deterministic executable oracle, a provider-selectable backend-level fault wrapper, live `serve` evidence for a two-scenario smoke, a local-safe provider matrix showing `serve` plus `ollama:qwen2.5:7b` live, an online matrix showing `codex-plan` operational on the clean-path benchmark, two-scenario injected-fault recovery evidence for `serve`, `ollama:qwen2.5:7b`, and `codex-plan`, a full six-scenario operational matrix for those three providers, and a granular metric surface for future sweeps. `claude-plan` is selectable but not operational in the current artifact, and `opencode` is not configured. The recorded artifacts do not yet prove the full Codex/Flywheel task comparison, Claude Code recovery, OpenCode recovery, 14B release-profile sweep, or 32B recovery under injected faults.
- mneme, relay, and plexus readiness reports exist as audit findings, but enterprise hardening is not complete.
- 14B and 32B publishing remains gated on release-grade benchmark evidence, model cards, checksums, packaging, and endpoint examples.

## Next Build Step

Run the backend-level fault wrapper against live agent/tool calls:

- Instantiate real `ServeBackend`, Ollama, endpoint-ladder, Codex CLI, Claude CLI, or OpenCode CLI backends through the existing backend factories.
- Inject timeout, rate-limit, malformed JSON, stale cache, and partial-result failures.
- Score retry, fallback, typed escalation, receipt completeness, and silent-failure avoidance.
- Run the same cases across Codex harness, flywheel harness, and local endpoints.
- Feed failures back into routing rules, model training/eval data, and smaller-package release criteria.
