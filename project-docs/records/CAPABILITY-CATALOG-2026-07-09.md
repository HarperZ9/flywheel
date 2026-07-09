# Capability Catalog - Codex/Flywheel Local-Model Harness

Date: 2026-07-09

Status: active catalog update, not a completion claim for the full program

## Purpose

This catalog records reusable capabilities that now exist in the local-model/flywheel environment, the evidence proving each capability, and the remaining promotion gaps. It separates verified facts from assumptions so future agents can route work without re-discovering the same surfaces.

## Capability: BuildLang/buildc receipt bridge

Capability id: `buildc_receipt_bridge`

Primary files:

- `C:\dev\local-model\harness\buildc_receipt_bridge.py`
- `C:\dev\local-model\scripts\run_buildc_receipt_bridge.py`
- `C:\dev\local-model\harness\accountability_bench.py`

What exists:

- Imports BuildLang/buildc receipt JSON into a flywheel byte-witness packet.
- Emits schema `buildlang-flywheel-byte-witness/v1`.
- Preserves buildc receipt schema, compiler identity, compiler version, language version, source path, source digest, input graph digest, invariant name/status, receipt status, seal presence, receipt hash, export hash, verifier command hash material, and a `transitive_witness.DepNode`-compatible node.
- Accepts UTF-8 with BOM JSON receipts.
- Fails closed: raw receipt import is `UNVERIFIABLE` unless buildc verification succeeds.
- Adds an accountability benchmark dimension, `buildc_receipt_bridge`, that scores whether the bridge refuses to promote unverified receipts to `MATCH`.

Verified evidence:

- Compile gate: `python -m py_compile harness/buildc_receipt_bridge.py scripts/run_buildc_receipt_bridge.py harness/accountability_bench.py scripts/run_m7_eval.py`
- Synthetic no-verify artifact: `C:\tmp\buildc_sample_flywheel_witness.json`, verdict `UNVERIFIABLE`.
- Synthetic verify-attempt artifact: `C:\tmp\buildc_sample_flywheel_witness_verify_attempt.json`, verdict `UNVERIFIABLE`.
- Real buildc receipt: `C:\tmp\buildc_heat_energy_receipt.json`.
- Real buildc measurement export: `C:\tmp\buildc_heat_energy_measurement_export.json`.
- Corrected real flywheel witness: `C:\tmp\buildc_heat_energy_flywheel_witness_with_export_v2.json`.
- Corrected witness verdict: `MATCH`.
- Corrected witness id: `0a65f06eb777c788c641d6da`.
- Corrected witness preserves source digest prefix `d1d746cdac277cad` and input graph digest prefix `79da5f861351df16`.

Known gaps:

- The bridge validates a single receipt packet at a time.
- Receipt chains are preserved as artifacts only when supplied; the bridge does not yet expand a buildc receipt chain into a full dependency DAG.
- The bridge does not yet write into a persistent receipt cache.
- The bridge does not yet run `buildc receipt corpus` or `buildc corpus verify`; it uses individual receipt verification.

Next promotion step:

- Add batch import for `buildc receipt chain` and `buildc receipt corpus` outputs, then fold them through `harness.transitive_witness`.

## Capability: M7 attached byte-witness scorecards

Capability id: `m7_attached_witness`

Primary file:

- `C:\dev\local-model\scripts\run_m7_eval.py`

What exists:

- `--attached-witness` accepts one or more byte-witness JSON packets.
- `--require-witness-match` fails source-mined/governed M7 runs unless every attached witness is a verified `MATCH` with a valid packet hash.
- Source-mined M7 scorecards include `attached_witnesses` and `summary.attached_witness_summary`.
- Governed-agent M7 scorecards include `attached_witnesses` and `summary.attached_witness_summary`.
- Scorecards preserve witness schema, packet hash, verdict, failure code, byte-witness id, receipt hash, export hash, and verification-attached status.
- Scorecards record `summary.witness_gate`, including pass/fail, reason, packet-hash validity, and failing witness paths.

Verified evidence:

- Source-mined live artifact: `C:\tmp\m7_buildlang_buildc_serve_codex_spark_live_with_witness_v2.json`.
- Source-mined attached witness summary: count `1`, loaded `1`, match rate `1.0`, unverifiable `0`, drift `0`.
- Source-mined live comparison: flywheel provider `serve` vs Codex provider `codex`; pass-rate delta `+1.0`, quality delta `+0.506`, latency delta `-57,695 ms`.
- Governed-agent live artifact: `C:\tmp\m7_governed_agent_serve_codex_spark_live_with_buildc_witness.json`.
- Governed-agent attached witness summary: count `1`, loaded `1`, match rate `1.0`, unverifiable `0`, drift `0`.
- Governed-agent deterministic release gate: `MATCH`, pass rate `1.0`, doc/schematic drift `1.0`, execution graph coverage `1.0`, organic doc update `1.0`, unauthorized writes `0`, unsafe mutations `0`.
- Governed-agent live comparison: flywheel provider `serve` vs Codex provider `codex`; pass-rate delta `+0.5`, quality delta `+0.352`, latency delta `-49,273 ms`.
- Witness gate compile validation: `python -m py_compile scripts/run_m7_eval.py scripts/make_adversarial_witness_fixtures.py`.
- Witness fixture output directory: `C:\tmp\adversarial_witness_fixtures`.
- Valid witness gate artifact: `C:\tmp\m7_witness_gate_match.json`, gate passed, `verified_match_count=1`.
- Drift witness gate artifact: `C:\tmp\m7_witness_gate_drift_should_fail.json`, gate failed with `verdict_DRIFT`.
- Tampered witness gate artifact: `C:\tmp\m7_witness_gate_tampered_should_fail.json`, gate failed with `packet_hash_mismatch`.
- Corrupt witness gate artifact: `C:\tmp\m7_witness_gate_corrupt_should_fail.json`, gate failed as `UNVERIFIABLE`.

Known gaps:

- Attached witnesses are scorecard metadata; backend responses are not yet required to consume or reason over the witness packet.
- Attached witness packets are not yet pushed into a centralized proof cache or dashboard.

Next promotion step:

- Feed witness packet contents into backend prompts and stateful tool-action checks so models must reason over the same packet that the M7 gate verifies.

## Capability: BuildLang/buildc source-mined benchmark lane

Capability id: `buildlang_buildc_compiler_receipts`

Primary files:

- `C:\dev\local-model\dataset\buildlang_buildc_sources_2026-07-09.json`
- `C:\dev\local-model\scripts\model_card_benchmark_shapes.py`
- `C:\dev\local-model\harness\source_mined_bench.py`
- `C:\dev\local-model\scripts\run_source_mined_benchmark.py`

What exists:

- Converts the actual local BuildLang/buildc corpus into a source-mined benchmark category.
- Preserves the local alias: `C:\dev\public\pubscan\quantalang` is the local checkout for public identity `HarperZ9/buildlang`.
- Scores local repo identity, buildc CLI coverage, receipt family coverage, MIR interlingua coverage, semantic corpus gates, backend maturity labeling, source-vs-aspirational boundary, Crucible/Telos export path, schematic alignment, and unsupported translation claims.

Verified evidence:

- Case-set validation: `16` cases, `13` categories, `100` unique metrics.
- Deterministic BuildLang oracle: `1/1` pass, `10` metrics.
- Live M7 artifact with corrected witness: `C:\tmp\m7_buildlang_buildc_serve_codex_spark_live_with_witness_v2.json`.

Known gaps:

- Deterministic oracle proves the metric surface, not that arbitrary models understand the compiler deeply.
- Live backend prompt checks are explanation-level, not direct buildc execution by the model.
- The lane currently has one case; it should split into receipt verification, MIR interlingua, backend maturity, extension-vs-compiler routing, and self-hosted-boundary subcases.

Next promotion step:

- Split `buildlang_buildc_compiler_receipts` into five independent cases so failures identify the exact compiler/harness concept that broke.

## Capability: Governed-agent workflow and schematic gate

Capability id: `governed_agent_workflow`

Primary files:

- `C:\dev\local-model\harness\governed_agent_bench.py`
- `C:\dev\local-model\scripts\run_governed_agent_benchmark.py`
- `C:\dev\local-model\scripts\run_m7_eval.py`

What exists:

- Deterministic governed-agent workflow benchmark.
- Maturity tiers: student, intern, supervised, autonomous.
- SQL/event state as source of truth.
- Vector memory as acceleration only.
- HITL gate, sandboxed skill mutation, fitness metrics, UI-state witness, and event receipts.
- Documentation/schematic drift gate.
- M7 governed-agent mode: `--governed-agent`.

Verified evidence:

- Live M7 governed artifact with attached buildc witness: `C:\tmp\m7_governed_agent_serve_codex_spark_live_with_buildc_witness.json`.
- Deterministic pass rate: `1.0`.
- Schematic release gate: `MATCH`.
- Backend rows: `serve` and `codex` live and operational.

Known gaps:

- Backend rows are explanation-plan checks, not full stateful agent execution.
- The deterministic state machine is local to the benchmark; it is not yet integrated as a runtime governance layer for arbitrary tools.

Next promotion step:

- Promote the deterministic governed workflow into a reusable runtime wrapper for tool actions, then score actual tool mutations instead of explanation text.

## Capability: Documentation and schematic maintenance standard

Capability id: `doc_schematic_maintenance`

Primary files:

- `C:\dev\local-model\project-docs\reports\DOCUMENTATION-SCHEMATIC-MAINTENANCE-STANDARD-2026-07-09.md`
- `C:\dev\local-model\project-docs\reports\EXPERIMENTAL-OUTCOME-CODEX-FLYWHEEL-LOCAL-ENGINE-2026-07-09.md`

What exists:

- Defines required promotion surfaces: `execution_graph`, `architecture_note`, `blast_radius`, and `receipt`.
- Adds benchmark variables: `docs_schematic_drift_score`, `execution_graph_coverage`, `organic_doc_update_score`, and `receipt_auditability_score`.
- Connects Decypher-style deterministic execution graphs and BuildLang/buildc receipt discipline into the harness roadmap.

Verified evidence:

- Governed-agent deterministic gate reports doc/schematic metrics at `1.0`.
- M7 governed-agent mode surfaces the schematic release gate inside a scorecard.

Known gaps:

- No persistent `project-docs/schematics/*.graph.json` files are generated yet.
- No CI-style drift check exists outside the benchmark runner.

Next promotion step:

- Add a schema and generator for `project-docs/schematics/architecture.graph.json`, then make M7/governed runs write the graph artifact.

## Capability: mneme, relay, plexus enterprise readiness audit

Capability id: `mneme_relay_plexus_readiness`

Primary file:

- `C:\dev\local-model\project-docs\enterprise\MNEME-RELAY-PLEXUS-READINESS-2026-07-08.md`

What exists:

- Current readiness report for mneme, relay, and plexus.
- Verified prototype test counts and primary gaps.
- Priority edit lists per tool.
- Shared enterprise definition of done.

Verified evidence:

- Mneme report states `82 passed in 3.36s`, wheel/CLI smoke, and `mneme bench` token reduction `0.7664` with recall `1.0`.
- Relay report states `53 passed in 4.37s` and `python -m relay --help` works.
- Plexus report states `31 passed in 0.07s`, CLI surfaces work, and manifest discovery round-trip works.

Known gaps:

- The report is an audit, not completed hardening.
- No new enterprise slice was implemented in this catalog update.

Next promotion step:

- Implement one bounded hardening slice, preferably `plexus` grounding and structured execution-plan output, because it connects directly to schematics and routing.

## Capability: Adversarial pressure weighted benchmarks

Capability id: `adversarial_pressure_weighted_benchmarks`

Primary files:

- `C:\dev\local-model\dataset\adversarial_pressure_sources_2026-07-09.json`
- `C:\dev\local-model\scripts\model_card_benchmark_shapes.py`
- `C:\dev\local-model\harness\source_mined_bench.py`
- `C:\dev\local-model\project-docs\reports\ADVERSARIAL-BENCHMARK-HARDENING-2026-07-09.md`

What exists:

- Seven adversarial benchmark lanes: proof integrity, graceful degradation, cross-harness consistency, tool-failure recovery, release/dataset provenance, schematic drift, and provider-refusal/accountability pressure.
- Case-level metric weights for high-risk failure modes.
- Backend scoring now emits `weighted_quality_score`, `graceful_degradation_score`, `receipt_witness_score`, and `adversarial_pressure_score`.
- Adversarial backend rows require either proof-backed success or explicit `UNVERIFIABLE` / `DRIFT` / typed escalation behavior.
- `scripts\make_adversarial_witness_fixtures.py` creates valid and adversarial byte-witness fixtures from a source packet.

Known gaps:

- Deterministic oracles prove the metric surface, not full live adversarial robustness.
- The backend lane still scores explanation text; deeper pressure should inject actual tampered witness files, stale graph artifacts, endpoint failures, and release folders.
- Only the first live two-category slice has been run; no full live Codex/Flywheel/Claude/OpenCode matrix has been rerun on all adversarial lanes yet.

Verified evidence:

- Case-set validation: `23` cases, `20` categories, `143` unique metrics.
- Deterministic adversarial validation: `7/7` pass, `49` metrics.
- Live M7 artifact: `C:\tmp\m7_adversarial_pressure_serve_codex_spark_live_n2.json`.
- Live slice comparison: flywheel `serve` vs Codex `gpt-5.3-codex-spark`; pass-rate delta `+0.5`, quality delta `+0.446`, latency delta `-21,992 ms`.
- Fixture generator validation: `C:\tmp\adversarial_witness_fixtures\buildc_heat_energy_match.json`, `buildc_heat_energy_unverifiable.json`, `buildc_heat_energy_drift.json`, `buildc_heat_energy_tampered_hash.json`, and `buildc_heat_energy_corrupt.json`.
- Full seven-lane provider matrix: `C:\tmp\m7_adversarial_pressure_full_provider_matrix_witness_gate.json`.
- Full matrix comparison: flywheel `serve` vs Codex Spark; pass-rate delta `+0.571`, quality delta `+0.355`, latency delta `-53,539.857 ms`.

Next promotion step:

- Run the adversarial category set across `serve`, `ollama`, `codex`, Claude Code, and OpenCode, then attach real tampered/valid witness packets and release-folder fixtures.

## Capability: Index timeout resilience

Capability id: `index_timeout_resilience`

Primary files:

- `C:\dev\public\index\src\index_graph\config.py`
- `C:\dev\public\index\src\index_graph\graph\walk.py`
- `C:\dev\public\index\src\index_graph\mcp.py`
- `C:\dev\public\index\src\index_graph\cache.py`
- `C:\dev\public\index\src\index_graph\router.py`
- `C:\dev\public\index\src\index_graph\cli_parser.py`
- `C:\dev\public\index\src\index_graph\cli_handlers\maps.py`
- `C:\dev\.repomap.toml`

What exists:

- Expanded generated-directory pruning for heavy build/cache directories, including Rust `target`.
- MCP result caching for expensive workspace-wide tools: `index.map`, `index.context`, `index.context.envelope`, `index_graph`, and `index_router`.
- Cache TTL is controlled by `INDEX_MCP_CACHE_TTL_SECONDS`; cache directory can be overridden by `INDEX_MCP_CACHE_DIR`.
- Shared CLI text cache for expensive router output, controlled by `INDEX_CACHE_TTL_SECONDS`; cache directory can be overridden by `INDEX_CACHE_DIR`.
- `index router --max-docs` bounds documentation-edge rendering; `--no-cache` forces a rebuild for measurement/debugging.
- MCP `index_router` accepts `max_docs`, so agent loops can request bounded context instead of receiving the full doc-edge dump.
- Router dependency labels are capped to prevent oversized per-node lines.

Verified evidence:

- Targeted validation: `python -m pytest tests/test_walk.py tests/test_scan.py tests/test_mcp.py -q` produced `26 passed`.
- Full router run: `python -m index_graph.cli router --root C:/dev --out C:/tmp/index_router_cdev_timeout_fix.md`.
- Observed elapsed time after prune expansion: `99,762 ms`.
- Earlier comparable router run before this fix: approximately `187.6 s`.
- Second-stage validation: `python -m py_compile src/index_graph/cache.py src/index_graph/router.py src/index_graph/cli_handlers/maps.py src/index_graph/cli_parser.py src/index_graph/mcp.py`.
- Focused router/MCP validation: `python -m pytest tests/test_router.py tests/test_router_deep_dives.py tests/test_mcp.py -q` produced `28 passed`.
- Bounded no-cache router: `python -m index_graph.cli router --root C:/dev --max-docs 500 --no-cache --out C:/tmp/index_router_cdev_bounded_nocache.md`, elapsed `82,320 ms`, size `71,531` bytes, `920` lines.
- Bounded cache-build router: `python -m index_graph.cli router --root C:/dev --max-docs 500 --out C:/tmp/index_router_cdev_bounded_cached.md`, elapsed `79,877 ms`, size `71,531` bytes, `920` lines.
- Bounded warm-cache router: `python -m index_graph.cli router --root C:/dev --max-docs 500 --out C:/tmp/index_router_cdev_bounded_cached2.md`, elapsed `246 ms`, size `71,531` bytes, `920` lines.

Known gaps:

- First-call router still takes roughly 80 seconds on `C:\dev` because graph build and doc discovery are full synchronous scans.
- The shared cache is output-level, not incremental graph/doc storage.
- Cache signatures are intentionally cheap workspace signatures; they are useful for closed-loop orientation, not a substitute for content-addressed proof receipts.

Next promotion step:

- Add incremental graph/doc artifact caching shared by CLI and MCP, with stale-state receipts instead of full rebuilds on every call.
- Store router/cache metadata in a receipt-like artifact so closed-loop agents can distinguish fresh, stale, bounded, and complete index views.

## Capability: Gather Discord source intake

Capability id: `gather_discord_source_intake`

Primary files:

- `C:\dev\public\gather\src\gather\discord.py`
- `C:\dev\public\gather\src\gather\run_config.py`
- `C:\dev\public\gather\src\gather\method.py`
- `C:\dev\public\gather\tests\test_discord.py`
- `C:\dev\public\gather\README.md`

What exists:

- Dedicated `discord` source adapter for `gather run` configs.
- Dedicated `discord_guild` source adapter for bounded guild/server channel discovery.
- Uses Discord's official REST messages endpoint for channel/thread intake.
- Uses Discord's official guild channels and active threads endpoints for guild/server intake.
- Reads bot credential only from `GATHER_DISCORD_BOT_TOKEN` by default.
- Sends the credential only as an `Authorization: Bot ...` header.
- Rejects targets containing the credential.
- Supports raw channel ids, `discord://channel/<id>`, and Discord channel URLs.
- Supports bounded pagination through `max_messages` and `page_size`.
- Supports bounded guild expansion through `max_channels`, `max_messages_per_channel`, and `page_size`.
- Emits one receipted `message` item per Discord message with source `discord`, method `discord-api-message`, and ref `channel:<id>`.
- Guild captures preserve `guild_id`, `channel_id`, `channel_name`, and `discord_source_kind` in message metadata.
- Includes human-readable message text plus canonical `raw_json` in the item body so the receipt hashes the observed API record, not only a summary.
- Explicitly avoids personal user-token scraping, selfbot access, browser-session scraping, and desktop UI scraping.

Verified evidence:

- Compile gate: `python -m py_compile src/gather/discord.py src/gather/run_config.py src/gather/method.py`.
- Focused validation: `python -m pytest tests/test_discord.py tests/test_api.py -q` produced `15 passed`.
- Tests cover target parsing, receipted item construction, malformed payload rejection, bot-header use, pagination, and credential non-leakage into URL/ref/text.
- Capture config for supplied Discord ids: `C:\dev\local-model\configs\gather-discord-redteam-context-2026-07-09.json`.
- Guild capture config for supplied Discord ids: `C:\dev\local-model\configs\gather-discord-redteam-guild-context-2026-07-09.json`.
- Integration report: `C:\dev\local-model\project-docs\reports\DISCORD-GATHER-INTEGRATION-2026-07-09.md`.
- Current environment credential check found no `GATHER_DISCORD_BOT_TOKEN` and no `DISCORD_TOKEN`.
- Command-level capture check reached the credential boundary and failed closed with `missing required credential in environment: GATHER_DISCORD_BOT_TOKEN`.

Example config:

```json
{
  "jobs": [
    {"source": "discord", "target": "1346756824233148527", "max_messages": 100}
  ],
  "store": "./corpus"
}
```

Known gaps:

- Live Discord intake has not been run in this session because no bot token was loaded into the environment.
- The adapter captures channel/thread messages only; guild inventory, forum post discovery, reactions, attachments download, and member joins are not implemented.
- Guild discovery captures text/news channels and active threads only; archived threads, forum post discovery, reactions, attachment download, and member joins are not implemented.
- Rate-limit handling is inherited from the current HTTP edge and should become typed retry/backoff receipt behavior.

Next promotion step:

- Add a federation registry row type for Discord channels and guilds, then run a live consented capture using a bot token in the local environment and store the resulting corpus receipt paths for benchmark synthesis.

## Capability: UnisonAI source-mined local-engine benchmark lanes

Capability id: `unisonai_source_mined_benchmarks`

Primary files:

- `C:\dev\local-model\dataset\unisonai_sources_2026-07-09.json`
- `C:\dev\local-model\scripts\model_card_benchmark_shapes.py`
- `C:\dev\local-model\scripts\run_source_mined_benchmark.py`
- `C:\dev\local-model\scripts\run_source_mined_backend_matrix.py`
- `C:\dev\local-model\scripts\run_m7_eval.py`
- `C:\dev\local-model\harness\source_mined_bench.py`
- `C:\dev\local-model\harness\unisonai_stateful_bench.py`
- `C:\dev\local-model\scripts\run_unisonai_stateful_benchmark.py`
- `C:\dev\local-model\tests\test_unisonai_stateful_bench.py`
- `C:\dev\local-model\project-docs\reports\UNISONAI-SOURCE-MINED-BENCHMARK-2026-07-09.md`

What exists:

- Public UnisonAI repository has been converted into benchmark pressure lanes rather than treated as verified performance evidence.
- New source-mined categories:
  - `teacher_exit_memory_ratchet`
  - `zero_parameter_corpus_law_eval`
  - `react_discord_interface_scope`
- New metrics cover correction permanence, negative-ledger behavior, teacher-exit evidence, fixed-item reproducibility, exact-count traceability, verification-suite coverage, same-machine comparison integrity, ReAct follow-through, Discord scope lock, interface/engine separation, tool trace receipts, and secret-boundary handling.
- M7 source-mined mode and backend matrix accept the UnisonAI dataset through default dataset loading.
- A deterministic stateful fixture now executes restart replay, negative-ledger withholding, teacher retirement by counted corrections, self-play non-reinforcement, fixed-item scorecard receipt reproducibility, Discord channel scope lock, tool-trace receipt generation, and secret-boundary checks.
- The stateful fixture now also supports backend-style JSON actions. It executes provider actions against the fixture and fails closed on malformed/prose-only output with `malformed_action_json`.
- The stateful action fixture now supports provider selectors through `--providers`, including `dry`, `serve`, `ollama`, `codex`, `claude`, `opencode`, and `open-code`.
- The stateful action fixture now supports an opt-in `--repair-json` pass that records original and repair response hashes, rejects empty action arrays, and only succeeds when repaired output is a non-empty executable action list.

Verified evidence:

- Compile gate: `python -m py_compile scripts/model_card_benchmark_shapes.py scripts/run_source_mined_benchmark.py scripts/run_source_mined_backend_matrix.py scripts/run_m7_eval.py harness/source_mined_bench.py`.
- Source-mined validation: `26` cases, `23` categories, `164` unique metrics.
- UnisonAI deterministic lanes: `3/3` pass, `21` metrics.
- M7 dry artifact: `C:\tmp\m7_unisonai_source_mined_dry.json`.
- M7 dry row: pass rate `0.333`, quality `0.378`, latency `0 ms`, failures `none:3`.
- Live provider matrix artifact: `C:\tmp\m7_unisonai_source_mined_provider_matrix.json`.
- Live matrix `serve` row: pass rate `1.0`, quality `0.748`, latency `43,329.667 ms`.
- Live matrix `ollama/qwen2.5:7b` row: pass rate `1.0`, quality `0.746`, latency `6,015 ms`.
- Live matrix `codex/gpt-5.3-codex-spark` row: pass rate `0.0`, quality `0.126`, latency `116,091 ms`, failures `timeout:2`, `low_task_focus:1`.
- Live matrix `claude` row: pass rate `0.0`, quality `0.0`, failures `quota_or_rate_limit:3`.
- Live matrix `opencode` row: skipped because no configured endpoint backend exists.
- Live matrix comparison: flywheel `serve` vs Codex Spark; pass-rate delta `+1.0`, quality delta `+0.622`, latency delta `-72,761.333 ms`.
- Stateful fixture command: `python scripts/run_unisonai_stateful_benchmark.py --state-root C:/tmp/unisonai_stateful_bench_state_20260709 --out C:/tmp/unisonai_stateful_benchmark_20260709.json --markdown-out C:/tmp/unisonai_stateful_benchmark_20260709.md`.
- Stateful fixture artifact: `C:\tmp\unisonai_stateful_benchmark_20260709.json`.
- Stateful fixture Markdown artifact: `C:\tmp\unisonai_stateful_benchmark_20260709.md`.
- Stateful fixture result: passed `True`, pass rate `1.0`, packet SHA-256 `4fcb9a6918322f078d17c715e9b9e87cdab1ad98797868556c5105d4198a7d8c`.
- Provider-action validation: `python -m pytest tests/test_unisonai_stateful_bench.py -q` produced `7 passed in 0.12s`.
- Provider-action input artifact: `C:\tmp\unisonai_stateful_backend_actions_20260709.json`.
- Provider-action benchmark artifact: `C:\tmp\unisonai_stateful_backend_benchmark_20260709.json`.
- Provider-action Markdown artifact: `C:\tmp\unisonai_stateful_backend_benchmark_20260709.md`.
- Provider-action result: passed `True`, pass rate `1.0`, packet SHA-256 `b7ec83974019af90149692db3fc96424531dc31b139e6dba3b64fe57b6117fef`.
- Provider-action fail-closed test: unstructured prose output returns failure class `malformed_action_json` and pass rate `0.0`.
- Dry provider action matrix artifact: `C:\tmp\unisonai_stateful_provider_matrix_dry_20260709.json`, operational rows `1`, mean pass rate `1.0`.
- Current provider action matrix artifact: `C:\tmp\unisonai_stateful_provider_matrix_all_20260709.json`, operational rows `1`, mean pass rate `0.2`.
- Current provider action matrix rows: `dry` passed with action count `8`; `serve`, `ollama`, and `codex` failed closed as `malformed_action_json`; `claude` failed as `provider_error` with low credit balance; `opencode` skipped due to no configured endpoint backend.
- Repair dry provider action matrix artifact: `C:\tmp\unisonai_stateful_provider_matrix_repair_dry_20260709_v2.json`, operational rows `1`, mean pass rate `1.0`.
- Repair current provider action matrix artifact: `C:\tmp\unisonai_stateful_provider_matrix_repair_all_20260709_v2.json`, operational rows `1`, mean pass rate `0.2`, repair attempted rows `3`, repair succeeded rows `0`, repair success rate `0.0`.
- Repair current provider action matrix rows: `dry` passed with action count `8`; `serve`, `ollama`, and `codex` attempted repair and still failed as `malformed_action_json`; `claude` failed as `provider_error` with low credit balance; `opencode` skipped due to no configured endpoint backend.
- Superseded repair artifact: `C:\tmp\unisonai_stateful_provider_matrix_repair_all_20260709.json` should not be used for conclusions because it came from the earlier permissive extraction path that accepted an empty action list during repair.

Known gaps:

- The dataset is based on public README-level claims, not a cloned local code audit.
- The deterministic oracle proves benchmark plumbing, not the source project's claimed empirical results.
- The earlier live source-mined provider matrix is still explanation-plan scoring; the new action matrix is stricter and currently shows live providers failing the executable JSON action contract.
- The repair lane is still prompt-based repair, not schema-constrained decoding or native tool-call output.
- No current live row repairs into non-empty executable actions, so planning quality remains unresolved behind the output-contract failure.
- Claude Code and OpenCode rows are endpoint/harness availability findings, not model-quality findings.

Next promotion step:

- Add a receipt-preserving schema-constrained output adapter or native tool-call lane, then rerun the UnisonAI action matrix to separate planning failures from formatting failures.

## Capability: OpenCode endpoint adapter activation

Capability id: `opencode_endpoint_adapter`

Primary files:

- `C:\dev\local-model\harness\endpoints.py`
- `C:\dev\local-model\tests\test_endpoints.py`
- `C:\dev\local-model\project-docs\reports\CLAUDE-OPENCODE-ENDPOINT-STATUS-2026-07-09.md`

What exists:

- `opencode` and `open-code` provider selectors are part of the endpoint ladder.
- OpenCode plan mode can use a reachable OpenCode desktop/server API through `OpenCodeBackend`.
- The backend targets the packaged server session/message surface: `POST /session`, `POST /session/{id}/message`, and `GET /session/{id}/message`.
- The adapter sends Basic auth only to the configured local OpenCode base URL.
- The adapter accepts both the harness-level env names and the packaged sidecar env aliases:
  - `OPENCODE_BASE_URL` or `OPENCODE_PORT`
  - `OPENCODE_USERNAME` / `OPENCODE_PASSWORD`
  - `OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`
  - `OPENCODE_PROVIDER_ID`
  - `OPENCODE_MODEL`
  - `OPENCODE_DIRECTORY`
  - `OPENCODE_AGENT`
- If `OPENCODE_PORT` is present and `OPENCODE_BASE_URL` is absent, the adapter resolves the base URL to `http://127.0.0.1:<port>`.

Verified evidence:

- User-supplied install path exists: `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe`.
- Installed package resources exist under `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop\resources`.
- Packaged archive scan found `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD` symbols in `app.asar`.
- Current environment probe found `OPENCODE_BASE_URL`, `OPENCODE_PORT`, `OPENCODE_PASSWORD`, `OPENCODE_SERVER_PASSWORD`, and `OPEN_CODE_CLI` unset.
- Current process probe found no running `OpenCode` process.
- Previous benchmark artifact still reflects the pre-activation state: OpenCode skipped because no configured endpoint backend existed.
- Desktop install fact: `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe` exists in the packaged Electron app directory, but no noninteractive endpoint was confirmed from that path alone.

Known gaps:

- No live OpenCode benchmark row has been produced yet because no reachable OpenCode sidecar/server and no sidecar password were present in the environment.
- The desktop executable is an Electron app, not a confirmed noninteractive terminal CLI.
- The OpenCode provider/model identifiers must match configured OpenCode providers before local 14B/32B or Spark rows can run through this harness path.

Next promotion step:

- Launch or expose the OpenCode sidecar with `OPENCODE_PORT` and `OPENCODE_SERVER_PASSWORD`, then rerun the UnisonAI source-mined slice with `--source-mined-providers opencode` against Spark and the local model provider configured in OpenCode.

## Capability: Enterprise harness control-plane architecture

Capability id: `enterprise_harness_architecture`

Primary files:

- `C:\dev\local-model\project-docs\ARCHITECTURE.md`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`
- `C:\dev\local-model\project-docs\schematics\architecture.graph.json`
- `C:\dev\local-model\scripts\run_pubscan_resource_profiles.py`
- `C:\dev\local-model\project-docs\reports\PUBSCAN-ZERO-DEPENDENCY-INTEGRATION-2026-07-09.md`

What exists:

- Authoritative architecture decision: one enterprise application surface backed by modular flagship services.
- Explicit boundary: flagships are not physically merged into one monolith; they are operated through typed adapters, shared API contracts, shared receipts, shared identity/config, shared observability, and shared UI.
- Zero-dependency boundary: core harness operation must work with local files, local executables, native rendering/tooling, local receipts, and local model endpoints; middleware and rich UI are optional adapters.
- Pubscan boundary: all top-level repositories under `C:\dev\public\pubscan` are first-class tool/repo surfaces and require `harness.tool-profile/v1` rows.
- Resource boundary: rendering/native tooling is treated as existing capability; compute and durable storage are the scarce resource layers that require explicit profiles.
- UI direction: instrument-panel control plane with Mission Control, Runs, Benchmarks, Models, Agents, Tools, Receipts, Schematics, and Settings/Auth.
- Frontend stack decision: native rendering/tooling plus CLI/TUI/static reports as core; React, TypeScript, Vite, graph library, and Tauri desktop are optional rich UI adapters.
- Backend stack decision: zero-dependency file-backed core first; optional Python/FastAPI control plane, worker runtime, endpoint adapter layer, receipt service, schematic service, and tool gateway.
- Data decision: local file/JSONL/SQLite store and content-addressed receipts are core authority; PostgreSQL is an optional authority adapter; vector/search stores are acceleration only.
- Infrastructure modes: `local-dev`, `local-enterprise`, `team-server`, and `airgap`.
- Machine-readable graph artifact: `harness.architecture-graph/v1`.
- Pubscan integration report: `C:\dev\local-model\project-docs\reports\PUBSCAN-ZERO-DEPENDENCY-INTEGRATION-2026-07-09.md`.
- Zero-dependency profile generator: `scripts\run_pubscan_resource_profiles.py`.
- Pubscan/resource profiles can be written directly into the file-backed receipt store with `--store-root`.

Verified evidence:

- `project-docs\ARCHITECTURE.md` and `project-docs\INFRASTRUCTURE.md` did not previously exist and have now been created as authoritative docs.
- `project-docs\schematics\architecture.graph.json` did not previously exist and has now been created as the initial graph artifact.
- Forum routing for this slice returned no single owner and identified the work as cross-domain across frontend, backend, cloud-infra, data-ml, technical-writing, and project-telos.
- Bounded `C:\dev\public\pubscan` inventory found `13` top-level directories: `calibrate-pro`, `emet`, `HarperZ9`, `HarperZ9.github.io`, `linguist`, `linguist-add-quantalang`, `quanta-color`, `quantalang`, `quantalang-tmLanguage`, `quantalang-vscode`, `quanta-universe`, `quanta-universe-fix-codegen-prefixing`, and `wol-pi`.
- Bounded `C:\dev` root inventory confirmed relevant corpus roots `C:\dev\public`, `C:\dev\tools`, and `C:\dev\local-model`; exact native rendering profile remains to be attached by receipt.
- Profile command added:

```powershell
python scripts/run_pubscan_resource_profiles.py --out C:/tmp/pubscan_resource_profiles_20260709.json --markdown-out C:/tmp/pubscan_resource_profiles_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- This is an architecture and infrastructure blueprint, not the implemented app shell.
- No FastAPI control-plane service, React UI shell, PostgreSQL schema, or worker queue has been implemented in this slice.
- The graph artifact is static v1 documentation; Plexus does not yet generate or validate it automatically.
- Pubscan/resource profile command has not been run in this slice because validation/probe execution was not explicitly requested.
- Native rendering/tooling is treated as existing capability, but the concrete rendering profile receipt still needs to be generated by the command.
- Compute/storage scarcity is documented, but resource profile receipts still need to be generated by the command.

Next promotion step:

- Run the zero-dependency profile command with `--store-root` to generate current pubscan, native-rendering, compute, and storage receipts directly into the file-backed Tool Registry seed.

## Current recursive loop state

Completed in this loop:

- BuildLang/buildc local corpus corrected and integrated.
- Buildc receipt bridge implemented.
- Real buildc scientific receipt emitted, verified, exported, bridged, and attached to M7.
- M7 source-mined and governed-agent scorecards can carry byte-witness packets.
- Adversarial pressure weighted benchmark lanes added.
- Gather Discord source intake added behind the official bot API boundary.
- UnisonAI source-mined benchmark lanes added and run across the live provider matrix.
- UnisonAI stateful execution fixture added and run once with passing deterministic evidence.
- UnisonAI provider-action fixture path added with focused tests and a scripted backend artifact.
- UnisonAI provider-selectable action matrix added and run across current `dry,serve,ollama,codex,claude,opencode` availability.
- UnisonAI repair-gated action matrix added and rerun; current live rows attempted repair but did not produce non-empty executable actions.
- OpenCode endpoint adapter activation improved for packaged sidecar env aliases and `OPENCODE_PORT`.
- Claude/Codex account lane status receipt command added for subscription/API preflight without exposing secrets.
- Enterprise harness architecture, infrastructure, and schematic graph docs added.
- Pubscan zero-dependency integration contract added and architecture corrected to zero mandatory external dependencies.
- Native rendering/tooling added as an existing capability surface; compute/storage named as explicit resource gaps.
- Pubscan/resource profile generator added.
- Pubscan/resource profile and endpoint-auth status scripts now accept `--store-root` and can write receipts/artifacts directly into the file-backed harness store.
- M7 and UnisonAI benchmark runners now accept `--store-root` and can write receipts/artifacts directly into the file-backed harness store.
- Closed-loop benchmark seed orchestrator now plans and runs the current context/profile/preflight/index/benchmark receipt sequence under one shared run id.
- Closed-loop outcome synthesizer now converts a seed run report into a Markdown/JSON experimental outcome draft with explicit observations, inferences, unknowns, and next checks.
- Context inventory command now records metadata-only scratch/temp/session/artifact context shapes into the file-backed store.
- Tool readiness command now records metadata-only flagship/pubscan enterprise-readiness posture into the file-backed store.
- Model release readiness command now records metadata-only 14B/32B publication-gate posture into the file-backed store.
- Gather readiness command now records metadata-only gather/source-intake posture into the file-backed store.
- Harness executable front-controller now exposes the current local-core receipt loop through `harness.cmd` and can emit a self-describing executable manifest receipt plus a static local HTML command registry.
- Capability catalog created.

Next loop:

- Split the BuildLang benchmark into multiple cases.
- Generate durable schematic graph artifacts.
- Start one bounded enterprise-hardening slice for mneme, relay, or plexus.
- Continue 14B/32B release evidence with model-card, checksum, endpoint, and benchmark gates.
- Run a live consented Discord capture through `gather` once `GATHER_DISCORD_BOT_TOKEN` is available in the local environment.
- Promote UnisonAI stateful provider rows from prompt repair to receipt-preserving schema-constrained output or native tool-call output.
- Produce a live OpenCode benchmark row once the sidecar/server is running with a known port and password.
- Run `scripts/run_pubscan_resource_profiles.py` to seed Tool Registry/resource profiles, then start the file-backed run/event/receipt store.

## Capability: Claude/Codex account lane status receipts

Capability id: `claude_codex_auth_status`

Primary files:

- `C:\dev\local-model\harness\endpoints.py`
- `C:\dev\local-model\scripts\run_endpoint_auth_status.py`
- `C:\dev\local-model\project-docs\reports\CLAUDE-OPENCODE-ENDPOINT-STATUS-2026-07-09.md`

What exists:

- Claude subscription account lane is represented by provider `claude`, mode `plan`, and the official Claude CLI.
- Claude API lane is represented by provider `claude`, mode `api`, and `ANTHROPIC_API_KEY`.
- Codex subscription account lane is represented by provider `codex`, mode `plan`, and the official Codex CLI.
- Codex/OpenAI API lane is represented by provider `codex`, mode `api`, and `OPENAI_API_KEY`.
- `scripts\run_endpoint_auth_status.py` emits `harness.endpoint-auth-status/v1` receipts without printing token or key values.
- `scripts\run_endpoint_auth_status.py` can write the status payload directly into the file-backed harness store with `--store-root`.
- Store receipt verdict is `AUTH_READY` when all lanes are configured and `AUTH_PARTIAL` otherwise.

Verified evidence:

- The endpoint ladder already exposes `claude` and `codex` plan/API modes through `harness.endpoints.build_endpoints`.
- The status script is present as a runnable receipt command:

```powershell
python scripts/run_endpoint_auth_status.py --out C:/tmp/harness_endpoint_auth_status_20260709.json --markdown-out C:/tmp/harness_endpoint_auth_status_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- The script has not been run in this update because validation/probe execution was not explicitly requested in the current auth-status slice.
- The script does not perform interactive sign-in; provider subscription auth remains inside the official CLI.
- The script does not inspect provider token stores and intentionally reports API key presence only as a boolean.

Next promotion step:

- Run the status command with `--store-root` to produce a current local receipt, then use the receipt as a preflight gate before Claude/Codex benchmark rows.

## Capability: Zero-dependency file-backed harness store

Capability id: `file_backed_harness_store`

Primary files:

- `C:\dev\local-model\harness\file_backed_store.py`
- `C:\dev\local-model\scripts\run_harness_file_store.py`
- `C:\dev\local-model\tests\test_file_backed_store.py`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`

What exists:

- Append-only local run/event/receipt store backed by plain files and JSONL.
- Content-addressed receipt bodies under `receipt-bodies/<sha256>.json`.
- Content-addressed copied artifacts under `artifacts/<sha256><suffix>`.
- Stable receipt `payload_sha256` for identical receipt kind/body payloads; timestamps are stored as metadata, not included in the content digest.
- Run records use schema `harness.run/v1`.
- Event records use schema `harness.event/v1`.
- Receipt records use schema `harness.receipt/v1`.
- Artifact records use schema `harness.artifact/v1`.
- Store initialization and snapshot command support through `scripts\run_harness_file_store.py`.
- No mandatory database, service, queue, package install, or network dependency.

Current-state evidence:

- Store implementation file exists at `C:\dev\local-model\harness\file_backed_store.py`.
- CLI wrapper exists at `C:\dev\local-model\scripts\run_harness_file_store.py`.
- Focused tests exist at `C:\dev\local-model\tests\test_file_backed_store.py`.
- Infrastructure doc includes file-store commands for initialization, snapshotting, and storing profile receipts.
- Runtime validation has not been run in this update because the current working rule forbids test/probe execution unless explicitly requested.

Example commands:

```powershell
python scripts/run_harness_file_store.py --store-root C:/tmp/harness_file_store --init --snapshot --out C:/tmp/harness_file_store_snapshot_20260709.json
```

```powershell
python scripts/run_harness_file_store.py --store-root C:/tmp/harness_file_store --receipt-json C:/tmp/pubscan_resource_profiles_20260709.json --receipt-kind pubscan_resource_profiles --receipt-verdict PROFILED --out C:/tmp/harness_file_store_pubscan_receipt_20260709.json
```

Known gaps:

- The store is append-only but does not yet expose run lifecycle transitions beyond creation.
- Receipts are local files, not yet merged into a queryable registry or dashboard.
- Artifact records are returned by the command but not yet appended to a dedicated `artifacts.jsonl` index.
- Artifact records are appended to `artifacts.jsonl` and can be queried by run id through `artifacts_for_run`.
- No lock file or concurrent-writer strategy exists yet.
- The store has not yet been wired as the default sink for M7, UnisonAI, gather, or OpenCode benchmark outputs.
- Pubscan/resource profiles, endpoint-auth status, M7, and UnisonAI now have direct store-sink flags, but those commands have not been run in this update.
- Tool readiness receipts now provide a static, store-backed preflight for index, forum, gather, crucible, telos, aleph, mneme, relay, plexus, and pubscan without running tool tests or reading source bodies.
- Model release readiness receipts now provide a static, store-backed preflight for the 14B and 32B publication tracks without hashing or copying large model files.
- Gather readiness receipts now provide a static, store-backed preflight for source intake without live capture or credential exposure.
- Harness executable front-controller now provides one Windows-friendly entrypoint for manifest, registry, plan, seed, outcome, query, and readiness commands.

Next promotion step:

- Run the pubscan/resource profile command and write its JSON output into this store as the first Tool Registry seed receipt, then promote benchmark runners to emit store receipts by default.

## Capability: Profile and preflight direct store sinks

Capability id: `profile_preflight_store_sinks`

Primary files:

- `C:\dev\local-model\scripts\run_pubscan_resource_profiles.py`
- `C:\dev\local-model\scripts\run_endpoint_auth_status.py`
- `C:\dev\local-model\tests\test_receipt_store_sinks.py`
- `C:\dev\local-model\harness\file_backed_store.py`

What exists:

- Pubscan/resource profile command accepts `--store-root` and `--run-id`.
- Endpoint-auth status command accepts `--store-root` and `--run-id`.
- Both commands write a file-backed receipt for the generated payload when `--store-root` is supplied.
- Both commands copy existing `--out` and `--markdown-out` files into the content-addressed artifact store when those paths are supplied.
- Pubscan/resource profiles use receipt kind `pubscan_resource_profiles` and verdict `PROFILED`.
- Endpoint-auth status uses receipt kind `endpoint_auth_status` and verdict `AUTH_READY` or `AUTH_PARTIAL`.
- Raw `--out` files remain raw evidence artifacts; `store_outputs` are attached to stdout only, avoiding self-referential artifact mutation after hashing.

Current-state evidence:

- Store sink helper tests exist in `C:\dev\local-model\tests\test_receipt_store_sinks.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example commands:

```powershell
python scripts/run_pubscan_resource_profiles.py --out C:/tmp/pubscan_resource_profiles_20260709.json --markdown-out C:/tmp/pubscan_resource_profiles_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_endpoint_auth_status.py --out C:/tmp/harness_endpoint_auth_status_20260709.json --markdown-out C:/tmp/harness_endpoint_auth_status_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- Store sinks are currently opt-in flags, not the default for every harness command.
- Benchmark runners still need equivalent `--store-root` support.
- Copied artifact records are queryable through `artifacts.jsonl`, but there is not yet a SQL/PostgreSQL adapter or dashboard query surface.

Next promotion step:

- Add equivalent `--store-root` sinks to gather capture commands and any remaining benchmark wrappers not routed through M7 or UnisonAI.

## Capability: Benchmark direct store sinks

Capability id: `benchmark_store_sinks`

Primary files:

- `C:\dev\local-model\harness\benchmark_receipts.py`
- `C:\dev\local-model\scripts\run_m7_eval.py`
- `C:\dev\local-model\scripts\run_unisonai_stateful_benchmark.py`
- `C:\dev\local-model\tests\test_benchmark_receipts.py`

What exists:

- Shared benchmark receipt helper writes benchmark payload receipts and optional artifacts to the file-backed harness store.
- Verdict inference preserves evidence honesty:
  - `BENCHMARK_PASS` / `BENCHMARK_FAIL` for direct deterministic pass flags.
  - `BENCHMARK_GATE_PASS` / `BENCHMARK_GATE_FAIL` for M7 witness-gated scorecards.
  - `BENCHMARK_PARTIAL` for matrices with failed or skipped rows.
  - `BENCHMARK_RECORDED` for valid recorded scorecards that are not all-pass gates.
- `scripts\run_m7_eval.py` accepts `--store-root` and `--run-id`.
- M7 standard scorecards store artifact receipts with kind `m7_scorecard`.
- M7 source-mined scorecards store receipts with kind `m7_source_mined_scorecard`.
- M7 governed-agent scorecards store receipts with kind `m7_governed_agent_scorecard`.
- `scripts\run_unisonai_stateful_benchmark.py` accepts `--store-root` and `--run-id`.
- UnisonAI deterministic, backend-action, and provider-matrix modes store receipts with distinct kinds derived from the output schema.
- Raw JSON/Markdown scorecards remain the artifact of record; store metadata is printed to stdout, not written back into the hashed benchmark artifact.

Current-state evidence:

- Helper exists at `C:\dev\local-model\harness\benchmark_receipts.py`.
- Focused behavior tests exist at `C:\dev\local-model\tests\test_benchmark_receipts.py`.
- M7 and UnisonAI runner flags have been added, but runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example commands:

```powershell
python scripts/run_m7_eval.py --source-mined --source-mined-providers serve,codex --source-mined-max-cases 2 --out C:/tmp/m7_source_mined_store_seed_20260709.json --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_m7_eval.py --governed-agent --governed-providers serve,codex --governed-backend-max-scenarios 2 --out C:/tmp/m7_governed_store_seed_20260709.json --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_unisonai_stateful_benchmark.py --providers dry,serve,ollama,codex,claude,opencode --repair-json --out C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json --markdown-out C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- Store sinks are opt-in flags, not the default.
- M7 standard scorecards currently store a metadata receipt plus the scorecard artifact instead of embedding the full scorecard JSON body in the receipt.
- Unified benchmark seed orchestration now exists for the current bounded evidence sequence, but it has not been run yet and does not cover the final full battery.

Next promotion step:

- Run the closed-loop orchestrator to create the first shared-run receipt bundle, then add a report synthesizer that turns those receipts into the experimental outcome document.

## Capability: Closed-loop benchmark seed orchestration

Capability id: `closed_loop_benchmark_seed_orchestration`

Primary files:

- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\tests\test_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\harness\file_backed_store.py`

What exists:

- One command builds the current closed-loop seed plan for endpoint auth, executable manifest, command registry, Forum route receipts, MCP tool health receipts, benchmark execution matrix, benchmark profile, context inventory, expanded tool readiness, tool hardening, local model endpoint/readiness/publish preflights, gather readiness, pubscan/resource profiles, Index CLI fallback, classifier-friction, M7 source-mined, M7 governed-agent, and UnisonAI stateful provider matrix.
- Normal execution creates a single file-backed run id and passes the same `--store-root` and `--run-id` into every child command.
- `--dry-plan` emits the exact planned commands without executing benchmarks or touching provider endpoints.
- Context inventory runs by default as a metadata-only preflight and can be disabled with `--skip-context-inventory`.
- Command registry generation runs by default as a metadata-only preflight and can be disabled with `--skip-harness-registry`.
- Benchmark execution matrix generation runs by default as a metadata-only preflight and can be disabled with `--skip-benchmark-execution-matrix`.
- Expanded tool readiness runs by default as a metadata-only preflight and can be disabled with `--skip-tool-readiness`.
- Model release readiness runs by default as a metadata-only preflight and can be disabled with `--skip-model-release-readiness`.
- Gather readiness runs by default as a metadata-only preflight and can be disabled with `--skip-gather-readiness`.
- Each executed step records start and finish events in the file-backed store.
- Each executed step captures stdout/stderr logs under the artifact directory and copies those logs into the content-addressed store.
- Final seed reports are copied into the content-addressed artifact store with label `closed-loop-seed-report-json`.
- Final report schema is `harness.closed-loop-benchmark-seed/v1`.
- Final receipt kind is `closed_loop_benchmark_seed`.
- Final orchestration verdict is `ORCHESTRATION_RECORDED` if all steps exit cleanly, otherwise `ORCHESTRATION_PARTIAL`.
- `--strict-exit` can convert partial orchestration into process exit failure for CI-style gating.

Current-state evidence:

- Orchestration command exists at `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`.
- Focused behavior tests exist at `C:\dev\local-model\tests\test_closed_loop_benchmark_seed.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example commands:

```powershell
python scripts/run_closed_loop_benchmark_seed.py --dry-plan --out C:/tmp/harness_closed_loop_seed_plan_20260709.json
```

```powershell
python scripts/run_closed_loop_benchmark_seed.py --store-root C:/tmp/harness_file_store --artifact-dir C:/tmp/harness_closed_loop_seed_20260709 --out C:/tmp/harness_closed_loop_seed_20260709.json --unisonai-repair-json
```

Known gaps:

- The orchestrator has not been run yet in this session.
- It seeds the current measurement loop but does not yet generate the final experimental outcome narrative from receipts.
- It does not yet include gather/Discord live capture, mneme/relay/plexus hardening runs, or live 14B/32B benchmark/checksum/endpoint release gates.
- The source-mined and governed defaults are intentionally bounded seed slices, not the final full benchmark battery.

Next promotion step:

- Run `--dry-plan` first, then execute the orchestrator to create the first shared-run receipt bundle. After that, add a report synthesizer that reads the store run and writes the experimental outcome document.

## Capability: Closed-loop outcome synthesis

Capability id: `closed_loop_outcome_synthesis`

Primary files:

- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`
- `C:\dev\local-model\tests\test_closed_loop_outcome_report.py`
- `C:\dev\local-model\harness\file_backed_store.py`

What exists:

- Reads a `harness.closed-loop-benchmark-seed/v1` JSON report.
- Can locate a seed report through the file-backed artifact index using `--store-root` and `--run-id` when no `--input` is supplied.
- Emits a structured `harness.closed-loop-outcome/v1` JSON outcome.
- Emits a Markdown experimental outcome document.
- Separates observations, inferences, unknowns, and next checks.
- Parses child JSON artifacts referenced by the seed report when those artifacts exist.
- Extracts M7 source-mined comparison blocks and provider metrics.
- Extracts M7 governed-agent comparison blocks and provider metrics.
- Extracts UnisonAI stateful provider-matrix rows, including provider, live/skipped/operational status, pass rate, failure class, and action count.
- Extracts benchmark execution matrix artifacts, including dry/focused/full step counts, long-running steps, operator-approval gates, provider roles, expected schemas, and evidence gates.
- Extracts context-inventory metadata signals, including inventory count, existing roots, observed entries, sensitive-name entries, and label counts.
- Extracts tool-readiness metadata signals, including observed tools, existing tools, enterprise-ready count, mean static score, and verdict counts.
- Extracts model-release metadata signals, including observed models, existing models, weight-file counts, release-doc score, benchmark artifact matches, and verdict counts.
- Extracts gather-readiness metadata signals, including gather root presence, config count, credential-presence booleans, core/Discord static scores, and verdict counts.
- Extracts command-registry metadata signals, including command count, command names, schema count, HTML artifact path, and risk counts.
- Keeps missing, unreadable, or non-JSON artifacts as explicit unloaded artifact observations.
- Marks dry plans as `OUTCOME_PLAN_ONLY`.
- Marks completed process-level runs as `OUTCOME_RECORDED`.
- Marks runs with failed or timed-out orchestration steps as `OUTCOME_PARTIAL`.
- Optionally stores the outcome as a file-backed receipt with kind `closed_loop_outcome`.
- Optionally copies JSON/Markdown outcome artifacts into the content-addressed store.

Current-state evidence:

- Outcome synthesizer exists at `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`.
- Focused behavior tests exist at `C:\dev\local-model\tests\test_closed_loop_outcome_report.py`.
- Tests now cover M7 source-mined comparison extraction and UnisonAI provider-matrix extraction.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_closed_loop_outcome_report.py --input C:/tmp/harness_closed_loop_seed_20260709.json --out C:/tmp/harness_closed_loop_outcome_20260709.json --markdown-out C:/tmp/harness_closed_loop_outcome_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_closed_loop_outcome_report.py --store-root C:/tmp/harness_file_store --run-id <run_id> --out C:/tmp/harness_closed_loop_outcome_20260709.json --markdown-out C:/tmp/harness_closed_loop_outcome_20260709.md
```

Known gaps:

- The synthesizer extracts known provider-level signals from M7 and UnisonAI child artifacts, but it does not yet parse every benchmark artifact shape in the repository.
- It does not replace the final experimental report required for the full program; it creates a seed outcome document from the current orchestration layer.
- It does not cover gather/Discord live capture or live 14B/32B benchmark/checksum/endpoint gates until those steps are added to orchestration.

Next promotion step:

- Extend the synthesizer to parse the remaining benchmark artifact shapes, then promote the seed outcome into the full experimental outcome document after a real closed-loop run is executed.

## Capability: Index CLI receipt fallback

Capability id: `index_cli_receipt_fallback`

Primary files:

- `C:\dev\local-model\scripts\run_index_receipt.py`
- `C:\dev\local-model\tests\test_run_index_receipt.py`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`
- `C:\dev\public\index\src\index_graph\cli_parser.py`
- `C:\dev\public\index\src\index_graph\mcp.py`

What exists:

- Receipt-backed fallback command for Index when the MCP transport returns `Transport closed` or otherwise degrades.
- Uses the existing Index CLI source of truth rather than inventing a second scanner.
- Supported lanes: `map`, `context`, `context-envelope`, `graph`, `check`, and `router`.
- Adds `C:\dev\public\index\src` to `PYTHONPATH` for the subprocess so the local checkout is used.
- Captures stdout/stderr as UTF-8 with replacement, preventing Unicode decode failures from crashing the harness receipt path.
- Emits schema `harness.index-cli-receipt/v1` with command, lane, root, index root, return code, elapsed time, output hashes, output byte counts, artifact path, output format, JSON parse status, verdict, and failure code.
- Preserves last-known-good context evidence on degraded runs. When a fresh Index CLI run times out, exits nonzero, emits empty stdout, or emits invalid JSON, a valid previous `--artifact-out` or explicit `--stale-artifact` is used as the effective output and the receipt emits `DEGRADED_MATCH` with `effective_output_source=stale_artifact`.
- Keeps live failure evidence separate from stale fallback evidence through `live_verdict`, `live_failure_code`, `effective_stdout_sha256`, `stale_artifact_sha256`, `stale_artifact_valid`, and `stale_artifact_used`.
- Can store the receipt and raw stdout artifact in the zero-dependency file-backed harness store.
- Preserves the stale artifact instead of overwriting it with empty or invalid live output when degraded fallback is active.
- Fails closed as `UNVERIFIABLE` on timeout, nonzero exit, empty output, or invalid JSON for JSON lanes when no valid stale artifact exists.
- Emits `MATCH` only when the CLI exits successfully and the output shape matches the lane.

Current-state evidence:

- The MCP failure observed in this session was `Transport closed` for `index.context.envelope`.
- `C:\dev\public\index\src\index_graph\mcp.py` maps `index.context.envelope` to the same internal context-envelope builder exposed by the CLI.
- `C:\dev\public\index\src\index_graph\cli_parser.py` exposes the required CLI lanes, including `context-envelope`, `router`, `map`, `context`, `graph`, and `check`.
- The fallback command and tests have been added, but not executed in this slice because validation/probe execution requires explicit user approval in this session.

Example commands:

```powershell
python scripts/run_index_receipt.py --lane context-envelope --root C:/dev/local-model --index-root C:/dev/public/index --budget 12000 --focus local-model --hops 2 --mcp-tool index_context_envelope --mcp-status transport_closed --mcp-error-code transport_closed --mcp-error-summary "Transport closed" --artifact-out C:/tmp/index_context_envelope_fallback_20260709.json --out C:/tmp/index_context_envelope_fallback_receipt_20260709.json --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_index_receipt.py --lane router --root C:/dev --index-root C:/dev/public/index --max-docs 500 --artifact-out C:/tmp/index_router_fallback_20260709.md --out C:/tmp/index_router_fallback_receipt_20260709.json --store-root C:/tmp/harness_file_store
```

Known gaps:

- This fallback does not fix the underlying MCP transport closure.
- The fallback still runs the potentially expensive Index CLI scan unless an Index cache is warm.
- The fallback stores raw stdout as an artifact; it does not yet split large Index outputs into queryable store rows.
- No default benchmark runner consumes this fallback automatically yet.

Next promotion step:

- Run the fallback command to produce a current `C:\dev` context-envelope receipt, then make benchmark and endpoint preflight scripts request the CLI fallback automatically when the Index MCP tool returns a transport error.

## Capability: 14B/32B model release readiness receipts

Capability id: `model_release_readiness_receipts`

Primary files:

- `C:\dev\local-model\scripts\run_model_release_readiness.py`
- `C:\dev\local-model\tests\test_model_release_readiness.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

What exists:

- Metadata-only release-readiness receipt command for the `14B` and `32B` local model publication tracks.
- Default model base root is `E:\local-model-run`, matching the current local model run surface.
- Checks model-root existence, top-level weight-file counts and byte sizes, release document presence, and benchmark/safety/release artifact-name matches.
- Does not read model file bodies, hash large model weights, run endpoints, or copy model artifacts into the file-backed store.
- Emits schema `harness.model-release-readiness/v1`.
- Uses receipt kind `model_release_readiness`.
- Direct command supports `--store-root` and `--run-id`.
- Closed-loop seed orchestration runs the model release preflight by default and can disable it with `--skip-model-release-readiness`.
- Closed-loop outcome synthesis extracts observed models, existing models, weight counts, release-doc score, benchmark artifact matches, release-ready count, and verdict counts.

Current-state evidence:

- `E:\local-model-run` exists.
- `C:\dev\local-model\models` does not exist.
- `C:\dev\local-model\model-cards` does not exist.
- `C:\dev\local-model\project-docs\model-cards` does not exist.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_model_release_readiness.py --models 14B,32B --base-root E:/local-model-run --artifact-roots "C:/dev/local-model/artifacts;C:/tmp" --out C:/tmp/model_release_readiness_20260709.json --markdown-out C:/tmp/model_release_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- This is a static preflight, not a live model quality benchmark.
- Large model files are not hashed yet; checksum readiness is represented by `checksums.sha256` presence only.
- Endpoint readiness is represented by `endpoint.json` presence only; the actual 14B/32B endpoints are not started or probed by this command.
- Publication readiness still requires model cards, provenance, license, checksums, endpoint profile, benchmark summary, safety notes, usage notes, and release checklist artifacts to exist and be backed by executed evidence.

Next promotion step:

- Add a live model-release gate that runs the 14B and 32B endpoints through the shared M7/UnisonAI benchmark tasks, records checksum receipts separately, and links those artifacts into this release-readiness receipt.

## Capability: Local model endpoint profile receipts

Capability id: `local_model_endpoint_profile_receipts`

Implemented files:

- `C:\dev\local-model\harness\model_profiles.py`
- `C:\dev\local-model\scripts\run_model_endpoint_profiles.py`
- `C:\dev\local-model\tests\test_model_endpoint_profiles.py`
- `C:\dev\local-model\scripts\run_model_release_readiness.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`

What changed:

- Adds metadata-only endpoint profile receipts for the 14B and 32B local model tracks.
- Integrates a distinct 32B serve reference path by defaulting 32B profiles to `http://127.0.0.1:8767` while keeping 14B on `http://127.0.0.1:8765`; both can be overridden explicitly.
- Emits `harness.model-endpoint-profiles/v1` with `serve` and `ollama` rows for each model.
- Records endpoint URLs, health/generate paths, launch command templates, provider roles, root existence, and agentic backend class names without probing endpoints or reading model file bodies.
- Extends model release readiness so endpoint profile artifacts can be attached to each 14B/32B release row.
- Extends `harness.cmd readiness` with target `model-endpoints`.
- Extends closed-loop seed orchestration so endpoint profiles are captured before model release readiness and passed into the release-readiness command.
- Extends closed-loop outcome synthesis so endpoint profile artifacts become first-class model endpoint signals.
- Extends benchmark profile coverage so `harness.model-endpoint-profiles/v1` artifacts map to the 14B/32B local model release gate.
- Adds a bounded live endpoint gate command, `scripts\run_model_endpoint_gate.py`, that probes existing `serve` and `ollama` endpoint profiles for health and one fixed generation without starting models or reading weights.
- Exposes that endpoint gate through the zero-dependency harness executable as `harness.cmd endpoint-gate`.
- Endpoint-gate failures fold gracefully by default: they are recorded as partial evidence while the process exits `0`; `--strict-exit` is available for release gates that must fail on unavailable endpoints.
- Extends closed-loop seed orchestration, benchmark coverage, and outcome synthesis to include `harness.model-endpoint-gate/v1`.
- Benchmark profile coverage now extracts endpoint-gate row providers, model units, and row counts instead of only recognizing the schema.
- Endpoint-gate rows now emit `quality_score` and deterministic `receipt_hash` fields, making them compatible with benchmark coverage's per-unit metric completeness and validity checks.
- Model release readiness now ingests `harness.model-endpoint-gate/v1` artifacts and records endpoint-gate row counts and generation-OK counts per model.
- Hardens endpoint gate backend construction so default local backend transports remain owned by `ServeBackend` and `OllamaBackend`; injected transports are used only by tests or explicit callers.
- Fixes local model root discovery to recognize the actual `E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct` and `E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct` layout.
- Hardens live endpoint gate rows with expected-vs-observed `model_ref` checks so a 14B serve process cannot satisfy a 32B release gate.
- Updates serve launch templates to include `SERVE_MODEL_ALIAS`, `SERVE_MODEL_REF`, and `SERVE_PORT`, including the 32B reference string `Qwen2.5-Coder-32B-Instruct (base, nf4)`.

### `classifier_friction_accountability_receipts`

- Promotes the existing classifier-friction benchmark into a first-class harness benchmark with schema `classifier-friction-benchmark/v1`.
- Adds deterministic `--out`, `--markdown-out`, `--store-root`, and `--run-id` support to `scripts\run_classifier_friction_benchmark.py`.
- Emits provider roles, explicit `task_id:mode` coverage units, top-level `quality_score`, `latency_ms`, `failure_class`, and `receipt_hash` fields for coverage accounting.
- Adds the benchmark to the weighted benchmark manifest, the executable command surface as `harness.cmd classifier-friction`, closed-loop seed orchestration, benchmark coverage, and outcome synthesis.
- Measures `guardrail_on`, `guardrail_off`, and `accountability_first` local prompt-layer modes without claiming provider-native guardrails are disabled.

### `harness_comparison_report_receipts`

- Adds `scripts\run_harness_comparison_report.py` with schema `harness.comparison-report/v1`.
- Ingests existing M7, UnisonAI, classifier-friction, and endpoint-gate JSON artifacts without rerunning models.
- Normalizes provider roles and computes Flywheel-minus-Codex pass-rate, quality, and latency deltas when both roles exist for the same comparison key.
- Treats missing counterpart rows as insufficient evidence rather than model-quality failure.
- Exposes the report as `harness.cmd comparison`, adds it to closed-loop seed orchestration, stores optional file-backed receipts, and surfaces comparison signals in closed-loop outcome synthesis.

### `mneme_relay_plexus_hardening_plan_receipts`

- Adds `scripts\run_tool_hardening_plan.py` with schema `harness.tool-hardening-plan/v1`.
- Consumes `harness.tool-readiness/v1` artifacts and converts observed missing files into prioritized actions.
- Separates observations from inferences for each action item and attaches owners, categories, and acceptance gates.
- Emits release gates for core, enterprise, integration, and action-closure status per tool.
- Exposes the generator as `harness.cmd tool-hardening`, adds it after `tool_readiness` in closed-loop seed orchestration, stores optional file-backed receipts, and surfaces action/owner counts in closed-loop outcome synthesis.
- Missing or unreadable readiness artifacts now produce `source_loaded=false`, preserve the load error, force `enterprise_ready_static=false`, and store as `TOOL_HARDENING_UNVERIFIABLE` rather than release-ready evidence.

### `model_publish_plan_14b_32b_receipts`

- Adds `scripts\run_model_publish_plan.py` with schema `harness.model-publish-plan/v1`.
- Consumes `harness.model-release-readiness/v1` artifacts and emits candidate names, slugs, release gates, blockers, required artifacts, and `DO_NOT_PUBLISH` / `READY_TO_STAGE` status.
- Defaults candidate names to `Flywheel-Local-Coder-14B` and `Flywheel-Local-Coder-32B` when those rows are present; the prefix is configurable through `--name-prefix`.
- Requires root, weights, complete release docs, endpoint profiles, endpoint generation OK, benchmark evidence, model card, README, license, checksums, provenance, endpoint docs, usage docs, benchmark summary, safety notes, and release checklist before staging.
- Does not publish models. `READY_TO_STAGE` only means the evidence is complete enough for an operator-gated staging decision.
- Exposes the generator as `harness.cmd model-publish`, adds it after `model_release_readiness` in closed-loop seed orchestration, stores optional file-backed receipts, and surfaces candidate-name/blocker counts in closed-loop outcome synthesis.

Why it matters:

- The executable harness now has a reproducible, secret-safe way to prove which local model endpoint paths exist before running 14B/32B agentic workflows.
- Release readiness can distinguish missing documentation from missing endpoint integration evidence.

Validation status:

- Focused tests were added or updated, but not run in this slice because validation/probe execution requires explicit user approval in this session.

## Capability: Gather/source-intake readiness receipts

Capability id: `gather_readiness_receipts`

Primary files:

- `C:\dev\local-model\scripts\run_gather_readiness.py`
- `C:\dev\local-model\tests\test_gather_readiness.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

What exists:

- Metadata-only gather/source-intake readiness receipt command.
- Default gather root is `C:\dev\public\gather`.
- Default config root is `C:\dev\local-model\configs`.
- Checks gather core surfaces, Discord adapter surfaces, capture config file metadata, and credential-presence booleans.
- Does not read config bodies, run gather, call Discord, scrape sources, or print credential values.
- Emits schema `harness.gather-readiness/v1`.
- Uses receipt kind `gather_readiness`.
- Direct command supports `--store-root` and `--run-id`.
- Closed-loop seed orchestration runs the gather readiness preflight by default and can disable it with `--skip-gather-readiness`.
- Closed-loop outcome synthesis extracts gather root presence, config count, credential presence, core score, Discord score, and verdict counts.

Current-state evidence:

- `C:\dev\public\gather` exists.
- `C:\dev\public\gather\src\gather\discord.py` exists.
- `C:\dev\public\gather\src\gather\run_config.py` exists.
- `C:\dev\public\gather\src\gather\method.py` exists.
- `C:\dev\public\gather\tests\test_discord.py` exists.
- `C:\dev\public\gather\README.md` exists.
- `C:\dev\local-model\configs\gather-discord-redteam-context-2026-07-09.json` exists.
- `C:\dev\local-model\configs\gather-discord-redteam-guild-context-2026-07-09.json` exists.
- Current shell environment did not expose `GATHER_DISCORD_BOT_TOKEN`.
- Current shell environment did not expose `DISCORD_TOKEN`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_gather_readiness.py --gather-root C:/dev/public/gather --config-roots C:/dev/local-model/configs --config-pattern "gather-*.json" --credential-vars GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN --out C:/tmp/gather_readiness_20260709.json --markdown-out C:/tmp/gather_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- This is a static preflight, not a live source capture.
- It records credential presence only as booleans; it intentionally does not inspect token stores or authenticate.
- It does not prove capture quality, source coverage, authorization-specific corpus completeness, or receipt chain quality.
- Live gather/Discord evidence still needs an executed gather run that emits receipted source items.

Next promotion step:

- Add a live gather receipt wrapper that runs bounded, configured source captures only when credentials are present, then links capture corpus receipts into the closed-loop outcome report.

## Capability: Zero-dependency harness executable front-controller

Capability id: `harness_executable_front_controller`

Primary files:

- `C:\dev\local-model\harness.cmd`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\tests\test_harness_cli.py`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`

What exists:

- Windows-friendly `harness.cmd` entrypoint at the repository root.
- Stdlib-only Python dispatcher at `scripts\run_harness_cli.py`.
- Subcommands for `plan`, `seed`, `outcome`, `query`, and `readiness`.
- `manifest` emits schema `harness.executable-manifest/v1`.
- `manifest` can write JSON/Markdown artifacts and an optional `harness_executable_manifest` receipt.
- Manifest rows include delegated scripts, output schemas, default artifact paths, long-running-risk labels, and recommended validation slices.
- `registry` emits a static local HTML command registry plus a machine-readable command/risk summary from the executable manifest and can store a `harness_command_registry` receipt.
- `registry` writes the default artifacts `C:\tmp\harness_command_registry.html` and `C:\tmp\harness_command_registry.json`.
- `execution-matrix` emits schema `harness.benchmark-execution-matrix/v1` through `scripts\run_benchmark_execution_matrix.py` without executing benchmarks.
- Closed-loop seed orchestration records the executable manifest by default and can disable it with `--skip-harness-manifest`.
- Closed-loop seed orchestration records the command registry by default and can disable it with `--skip-harness-registry`.
- Closed-loop seed orchestration records the benchmark execution matrix by default and can disable it with `--skip-benchmark-execution-matrix`.
- Closed-loop outcome synthesis extracts executable command names, schema count, target count, and evidence surfaces.
- Closed-loop outcome synthesis extracts command registry names, risk counts, schema count, and HTML artifact paths.
- `plan` delegates to `scripts\run_closed_loop_benchmark_seed.py --dry-plan`.
- `seed` delegates to `scripts\run_closed_loop_benchmark_seed.py`.
- `outcome` delegates to `scripts\run_closed_loop_outcome_report.py`.
- `query` delegates to `scripts\run_harness_store_query.py`.
- `readiness` delegates to context, tool, model-release, gather, endpoint-auth, and pubscan readiness/profile commands.
- Global `--print-command` prints the delegated command without executing it.
- No PyInstaller, Node, Docker, database, service, or packaging dependency is required.

Current-state evidence:

- `harness.cmd` exists as a command wrapper over `scripts\run_harness_cli.py`.
- `scripts\run_harness_cli.py` exists and builds delegated commands for the current local-core receipt loop.
- Focused tests exist at `C:\dev\local-model\tests\test_harness_cli.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example commands:

```powershell
.\harness.cmd manifest --out C:/tmp/harness_executable_manifest.json --markdown-out C:/tmp/harness_executable_manifest.md --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd registry --out C:/tmp/harness_command_registry.html --summary-out C:/tmp/harness_command_registry.json --store-root C:/tmp/harness_file_store
```

```powershell
.\harness.cmd --print-command plan --out C:/tmp/harness_closed_loop_seed_plan.json
```

```powershell
.\harness.cmd seed --store-root C:/tmp/harness_file_store --artifact-dir C:/tmp/harness_closed_loop_seed --out C:/tmp/harness_closed_loop_seed.json --unisonai-repair-json
```

```powershell
.\harness.cmd outcome --input C:/tmp/harness_closed_loop_seed.json --out C:/tmp/harness_closed_loop_outcome.json --markdown-out C:/tmp/harness_closed_loop_outcome.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- This is a local-core executable front-controller, not a signed standalone binary.
- It assumes `python` is available on the operator workstation.
- It does not start or manage long-running services.
- It does not yet expose a TUI/UI, model endpoint lifecycle management, or live benchmark profile selection beyond the current command flags.

Next promotion step:

- Promote the static registry into a native launch surface that can start safe commands, require deliberate confirmation for high-risk commands, and stream file-store run events.

## Capability: Weighted benchmark profile manifest

Capability id: `weighted_benchmark_profile_manifest`

Primary files:

- `C:\dev\local-model\scripts\run_benchmark_profile_manifest.py`
- `C:\dev\local-model\tests\test_benchmark_profile_manifest.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

What exists:

- Metadata-only benchmark contract command for the Codex/Flywheel local-model loop.
- Emits schema `harness.benchmark-profile-manifest/v1`.
- Records the provider matrix for `serve`, `codex`, `ollama`, `claude`, `opencode`, and `dry` by default.
- Records stable provider roles and aliases so raw provider names normalize into `flywheel`, `codex`, `ollama_local`, `claude_code`, `opencode`, and `dry_fixture`.
- Defines weighted measurement variables for task completion, quality, groundedness, tool-use success, workflow state management, reliability, failure-mode clarity, latency, cost/resource use, reproducibility, and accountability receipts.
- Defines weighted dataset lanes for source-mined codebase tasks, agentic tool workflows, adversarial receipt integrity, endpoint release gates, guardrail/accountability friction, local resource pressure, and cross-harness reproducibility.
- Exposes pressure variables such as large context, stale docs, malformed JSON, tool timeout, false match, receipt drift, endpoint down, missing checksum, over-compliance, low VRAM, adapter skew, and schema mismatch.
- Defines seed benchmark rows for M7 source-mined, M7 governed-agent, UnisonAI stateful provider matrix, and classifier-friction accountability.
- Defines planned full-suite rows for adversarial pressure, 14B/32B release gates, gather live source intake, long-horizon closed-loop agentic workflows, cross-harness reproducibility, local resource pressure, and toolchain failure recovery.
- Declares per-benchmark `coverage_units` so provider-level scorecards can be checked against expected case/scenario coverage.
- Inventories existing benchmark-like JSON artifact names under configured roots without reading artifact bodies.
- Supports JSON and Markdown outputs plus optional file-backed store receipt kind `benchmark_profile_manifest`.
- `harness.cmd benchmarks` delegates to the profile command.
- Closed-loop seed orchestration records the benchmark profile by default and can disable it with `--skip-benchmark-profile`.
- Closed-loop outcome synthesis extracts benchmark profile providers, metric names, metric weight sums, dataset lane weight sums, dataset lanes, pressure variables, runnable/planned benchmark counts, coverage-unit counts, existing artifact counts, and benchmark ids.

Current-state evidence:

- Files have been added or updated for the benchmark profile manifest and closed-loop integration.
- Focused tests exist at `C:\dev\local-model\tests\test_benchmark_profile_manifest.py`, `C:\dev\local-model\tests\test_harness_cli.py`, `C:\dev\local-model\tests\test_closed_loop_benchmark_seed.py`, and `C:\dev\local-model\tests\test_closed_loop_outcome_report.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_benchmark_profile_manifest.py --providers serve,codex,ollama,claude,opencode,dry --artifact-roots "C:/tmp;C:/dev/local-model/artifacts" --out C:/tmp/benchmark_profile_manifest_20260709.json --markdown-out C:/tmp/benchmark_profile_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- This artifact defines benchmark rigor and discovers artifact names; it does not run benchmarks or prove model quality.
- Existing artifact inventory is intentionally metadata-only and top-level bounded; it does not parse historical scorecard contents.
- The full benchmark battery still requires executed M7, UnisonAI, adversarial, gather, and 14B/32B endpoint/release gates.
- Weight values are a harness policy baseline and should be reviewed after live result variance is measured.

Next promotion step:

- Add a benchmark-profile diff report that compares the defined contract against executed scorecards and flags missing provider/model/task coverage.

## Capability: Benchmark profile coverage report

Capability id: `benchmark_profile_coverage_report`

Primary files:

- `C:\dev\local-model\scripts\run_benchmark_profile_coverage.py`
- `C:\dev\local-model\tests\test_benchmark_profile_coverage.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

What exists:

- Compares a `harness.benchmark-profile-manifest/v1` contract against observed scorecard/readiness artifacts.
- Emits schema `harness.benchmark-profile-coverage/v1`.
- Maps known artifact schemas to benchmark ids: M7 source-mined, M7 governed-agent, UnisonAI stateful provider matrix, model release readiness, and gather readiness.
- Extracts observed providers from non-skipped M7 backend rows and non-skipped UnisonAI provider rows.
- Reports declared runnable benchmark ids, observed benchmark ids, missing runnable benchmark ids, declared coverage units, observed coverage units, missing coverage units, per-unit metric completeness, per-unit metric validity, expected provider roles, raw expected providers, observed provider roles, missing provider roles, provider-by-unit coverage, provider-by-unit validity, declared/observed/missing dataset lanes, declared/observed/missing pressure variables, coverage rates, load errors, and verdict.
- Uses verdict `COVERAGE_COMPLETE` only when runnable benchmark coverage, provider coverage, unit coverage, per-unit metric completeness, per-unit metric validity, provider-by-unit coverage, provider-by-unit validity, dataset-lane coverage, pressure-variable coverage, and artifact loading all pass.
- Uses verdict `COVERAGE_PARTIAL` when expected scorecards or providers are missing.
- Uses verdict `COVERAGE_UNVERIFIABLE` when the profile itself cannot be loaded.
- Supports JSON and Markdown outputs plus optional file-backed store receipt kind `benchmark_profile_coverage`.
- `harness.cmd benchmark-coverage` delegates to the coverage command.
- Closed-loop seed orchestration records benchmark coverage after scorecard steps by default and can disable it with `--skip-benchmark-coverage`.
- Closed-loop outcome synthesis extracts benchmark coverage rates, unit coverage rates, unit metric completeness rates, unit metric validity rates, provider-by-unit coverage rates, provider-by-unit validity rates, dataset-lane coverage rates, pressure-variable coverage rates, missing runnable benchmark ids, missing providers, missing dataset lanes, missing pressure variables, missing units, incomplete units, invalid units, missing provider units, invalid provider units, load errors, observed ids, and verdict counts.

Current-state evidence:

- Files have been added or updated for the benchmark profile coverage report and closed-loop integration.
- Focused tests exist at `C:\dev\local-model\tests\test_benchmark_profile_coverage.py`, `C:\dev\local-model\tests\test_harness_cli.py`, `C:\dev\local-model\tests\test_closed_loop_benchmark_seed.py`, and `C:\dev\local-model\tests\test_closed_loop_outcome_report.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_benchmark_profile_coverage.py --profile C:/tmp/benchmark_profile_manifest_20260709.json --artifacts "C:/tmp/m7_source_mined_store_seed_20260709.json;C:/tmp/m7_governed_store_seed_20260709.json;C:/tmp/unisonai_stateful_provider_matrix_store_seed_20260709.json" --out C:/tmp/benchmark_profile_coverage_20260709.json --markdown-out C:/tmp/benchmark_profile_coverage_20260709.md --store-root C:/tmp/harness_file_store
```

Known gaps:

- Coverage proves whether expected evidence is present; it does not score quality for present evidence.
- Schema-to-benchmark-id mapping is currently explicit and should be extended when new benchmark artifact schemas are added.
- Provider coverage is extracted from non-skipped scorecard rows only; static readiness artifacts and skipped provider rows do not count as provider execution.
- Unit coverage depends on scorecards exposing `case_id`, `scenario_id`, `coverage_unit`, `coverage_unit_id`, `benchmark_case_id`, `case_category`, or `category` fields inside known result containers.
- Metric completeness requires each observed declared unit to expose quality, latency, failure-class/verdict, and receipt/witness evidence. An empty `failure_class` value counts as explicit no-failure evidence when the field exists.
- Metric validity requires quality values in `[0, 1]`, non-negative latency, recognized typed failure/verdict values, and receipt/witness identifiers with valid hash-like or non-empty witness shapes.
- Provider-by-unit coverage only counts non-skipped result rows that connect a provider id to a declared coverage unit. Provider rows without unit ids and unit rows without provider ids do not satisfy this stricter gate.
- Provider aliases normalize raw provider strings like `serve`, `flywheel`, `codex`, `gpt-5.3-codex-spark`, `claude-code`, `open-code`, `ollama`, and `dry` into stable role ids before coverage rates are computed.

Next promotion step:

- Extend provider-role normalization into every remaining benchmark runner so scorecards emit canonical roles directly instead of relying only on downstream normalization.

## Capability: Shared benchmark provider roles

Capability id: `shared_benchmark_provider_roles`

Implemented files:

- `C:\dev\local-model\harness\provider_roles.py`
- `C:\dev\local-model\tests\test_provider_roles.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_manifest.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_coverage.py`
- `C:\dev\local-model\scripts\run_m7_eval.py`
- `C:\dev\local-model\scripts\run_unisonai_stateful_benchmark.py`

What changed:

- Centralizes provider aliases and canonical role ids in `harness.provider_roles`.
- Normalizes raw selectors such as `serve`, `codex`, `gpt-5.3-codex-spark`, `open-code`, `ollama`, `claude-code`, and `dry` into stable roles: `flywheel`, `codex`, `opencode`, `ollama_local`, `claude_code`, and `dry_fixture`.
- M7 governed-agent, M7 source-mined, and UnisonAI provider-matrix scorecards now stamp `provider_role` into row-level evidence while preserving the raw `provider` selector.
- M7 source-mined now emits `backend_rows` alongside its existing `rows` field so benchmark-profile coverage can read the same provider-row shape as governed-agent scorecards.
- Benchmark profile and benchmark coverage now share the same role map, with coverage retaining profile-level aliases as overrides when present.

Why it matters:

- Codex-vs-flywheel-vs-OpenCode-vs-Claude-vs-local comparisons now have one canonical provider identity layer instead of script-local string handling.
- Coverage rates can compare expected provider roles against observed scorecards without misclassifying equivalent selectors.

Validation status:

- Focused tests were added or updated, but not run in this slice because validation/probe execution requires explicit user approval in this session.

## Capability: Benchmark execution matrix

Capability id: `benchmark_execution_matrix`

Primary files:

- `C:\dev\local-model\scripts\run_benchmark_execution_matrix.py`
- `C:\dev\local-model\tests\test_benchmark_execution_matrix.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\tests\test_harness_cli.py`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`

What exists:

- Emits schema `harness.benchmark-execution-matrix/v1`.
- Does not execute providers, endpoints, or benchmarks.
- Defines dry, focused, and full run tiers with exact command arrays and shell-ready command text.
- Records providers, normalized provider roles, aliases, expected artifact paths, expected output schemas, evidence gates, and operator-approval requirements.
- Includes the Index CLI fallback context receipt, local 14B/32B endpoint profiles, closed-loop dry plan, focused closed-loop seed, classifier-friction matrix, local 14B/32B endpoint gate with model-ref validation, benchmark coverage, harness comparison, outcome synthesis, and full-provider matrix promotion command.
- Exposes the generator through `harness.cmd execution-matrix`.
- Closed-loop seed orchestration records the matrix by default as a metadata-only preflight and can disable it with `--skip-benchmark-execution-matrix`.
- Closed-loop outcome synthesis parses matrix artifacts and surfaces benchmark execution matrix signals in Markdown experimental outcomes.
- Store integration uses receipt kind `benchmark_execution_matrix` and verdict `BENCHMARK_EXECUTION_MATRIX_RECORDED`.

Current-state evidence:

- Files have been added or updated for the benchmark execution matrix and harness CLI integration.
- Focused tests exist at `C:\dev\local-model\tests\test_benchmark_execution_matrix.py` and `C:\dev\local-model\tests\test_harness_cli.py`.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

Example command:

```powershell
python scripts/run_benchmark_execution_matrix.py --providers serve,codex,ollama,claude,opencode,dry --run-id benchmark_matrix_20260709 --artifact-dir C:/tmp/harness_benchmark_matrix_20260709 --out C:/tmp/benchmark_execution_matrix_20260709.json --markdown-out C:/tmp/benchmark_execution_matrix_20260709.md --store-root C:/tmp/harness_file_store
```

## Capability: Roadmap status ledger

Capability id: `roadmap_status_ledger`

Primary files:

- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md`

What exists:

- Adds a durable roadmap status record for the Codex/Flywheel local-model harness program.
- Separates observed evidence from incomplete work and missing gates.
- Tracks major workstreams on a `0` to `4` planning scale so roadmap status is not only chat prose.
- Audits the required final outputs from the active objective against current evidence and next gates.
- Records `index` MCP `Transport closed` as an active integration risk while preserving the local fallback path as mitigation.

Current-state evidence:

- The roadmap status record exists at `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`.
- The status record intentionally does not claim benchmark execution, endpoint health, test pass, package release, or model publishing completion.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

## Capability: Required-output integration reports

Capability id: `required_output_integration_reports`

Primary files:

- `C:\dev\local-model\project-docs\records\TOOL-INTEGRATION-REPORT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\HARNESS-ARCHITECTURE-ENDPOINT-REPORT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md`

What exists:

- Adds the first durable tool integration report required by the active objective.
- Adds the first durable harness architecture and endpoint report required by the active objective.
- Records observed local roots for `aleph`, `local-model`, public `crucible`, `forum`, `gather`, `index`, `mneme`, `plexus`, `relay`, `telos`, `pubscan`, and `tools`.
- Separates scaffolded harness integration from live execution proof.
- Updates the roadmap status ledger so the required-output audit marks these reports as drafted rather than only partial.

Current-state evidence:

- The reports exist under `C:\dev\local-model\project-docs\records`.
- The reports intentionally do not claim benchmark execution, endpoint health, or tool readiness pass status.
- Runtime validation has not been run in this update because validation/probe execution requires explicit user approval in this session.

## Capability: Required-output draft pack

Capability id: `required_output_draft_pack`

Primary files:

- `C:\dev\local-model\project-docs\records\WORKSPACE-CONTEXT-MAP-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CODEX-FLYWHEEL-BENCHMARK-COMPARISON-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\LOCAL-MODEL-BENCHMARK-SUMMARY-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\MNEME-READINESS-REPORT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\RELAY-READINESS-REPORT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\PLEXUS-READINESS-REPORT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\MODEL-NAMING-PUBLISHING-PLAN-14B-32B-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\EXPERIMENTAL-OUTCOME-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-07-09.md`

What exists:

- Adds draft records for every remaining required final-output lane that did not yet have a durable artifact.
- Marks Codex-vs-Flywheel, local model, and experimental outcome documents as no-result drafts until real benchmark artifacts exist.
- Adds separate readiness drafts for mneme, relay, and plexus, with shipped-change claims explicitly set to none.
- Adds a model naming and publishing plan for 14B/32B with do-not-publish gates.
- Updates the roadmap status ledger from approximately `53%` to approximately `59%` because the documentation/deliverable surface is more complete, while execution evidence remains incomplete.

Current-state evidence:

- These records were added as documentation artifacts only.
- No tests, endpoint probes, model runs, benchmark runs, package builds, or release gates were executed in this update.

## Capability: Forum ledger deep-verify benchmark lane

Capability id: `forum_ledger_deep_verify_benchmark_lane`

Primary files:

- `C:\dev\local-model\project-docs\records\FORUM-LEDGER-DEEP-VERIFY-BENCHMARK-PLAN-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\FORUM-FEEDBACK-REPLY-DRAFT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`
- `C:\dev\public\forum\src\forum\ledger.py`
- `C:\dev\public\forum\src\forum\storage.py`
- `C:\dev\public\forum\src\forum\report.py`
- `C:\dev\public\forum\src\forum\cli.py`

What exists:

- Converts external feedback about `forum` content-addressing and `verify(deep=True)` scaling into a first-class benchmark lane.
- Records that current local evidence shows functional deep verification, content-addressed redaction, durable `FileStorage`, and ledger A/B summary comparison.
- Records that current local evidence does not show a dedicated deep-verify scaling benchmark with entry-count, payload-size, redaction-ratio, storage-mode, warm/cold, and negative-control dimensions.
- Adds a public-facing answer draft that distinguishes implemented integrity behavior from unmeasured scaling behavior.

Current-state evidence:

- Source inspection shows `Ledger.verify(deep=True)` performs chain verification and then re-hashes present payload bodies through `verify_payloads()`.
- Source inspection shows `FileStorage` loads JSONL entries and payloads into memory on construction and serves ledger reads from memory.
- Source inspection shows `forum bench` compares summarized ledger metrics, not deep-verify timing.
- No benchmark, test, endpoint probe, or performance run was executed in this update.

## Capability: Custom agentic benchmark task set

Capability id: `custom_agentic_benchmark_task_set`

Primary files:

- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`
- `C:\dev\local-model\project-docs\records\AGENTIC-BENCHMARK-TASK-SET-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Adds a machine-readable custom agentic benchmark task set with schema `harness.agentic-task-set/v1`.
- Defines twelve tasks spanning Index fallback integrity, forum deep-verify scaling, Codex-vs-Flywheel same-task comparison, 14B/32B endpoint gates, mneme/relay/plexus enterprise readiness, receipts-vs-guardrails friction, documentation/schematic maintenance, OpenCode adapter readiness, and local-resource pressure.
- Attaches each task to dataset lanes, required inputs, expected artifacts, scoring focus, and must-not constraints.
- Updates the roadmap estimate to approximately `63%` because the benchmark corpus is now concrete, while execution evidence remains missing.

Current-state evidence:

- The benchmark corpus is a draft data artifact and has not been executed.
- The `benchmarks` directory did not exist before this artifact was added in this slice.
- No benchmark runner, adapter, test, endpoint probe, or provider run was executed in this update.

## Capability: Agentic task-set adapter contract

Capability id: `agentic_task_set_adapter_contract`

Primary files:

- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`
- `C:\dev\local-model\project-docs\records\AGENTIC-TASK-SET-ADAPTER-PLAN-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Defines a non-executing adapter contract that maps `harness.agentic-task-set/v1` tasks into benchmark ids, coverage units, dataset lanes, expected artifacts, and future scorecard rows.
- Defines planned schema `harness.agentic-task-manifest/v1` for dry, provider-free task expansion.
- Defines planned schema `harness.agentic-task-scorecard/v1` for executed or imported task results.
- Defines how the task set should connect to benchmark profile, benchmark coverage, closed-loop seed, and outcome synthesis.
- Raises the roadmap estimate to approximately `64%` because the custom task set now has a concrete adapter boundary, while execution evidence remains absent.

Current-state evidence:

- The adapter is a draft data/documentation artifact.
- No adapter script, production code, test, endpoint probe, benchmark run, or provider call was executed in this update.

## Capability: Agentic task-set adapter implementation runbook

Capability id: `agentic_task_set_adapter_implementation_runbook`

Primary files:

- `C:\dev\local-model\benchmarks\agentic-task-set-implementation-plan-v1.json`
- `C:\dev\local-model\project-docs\records\AGENTIC-TASK-SET-IMPLEMENTATION-RUNBOOK-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md`

What exists:

- Converts the adapter contract into an implementation-ready, non-executing runbook.
- Names the future script, harness subcommand, schemas, target production files, target test files, documentation files, and test-first sequence.
- Defines the exact non-execution guardrail: no provider calls, no endpoint probes, no model weight reads, no benchmark execution, and no success claims from manifest generation.
- Raises the roadmap estimate to approximately `65%` because the benchmark corpus now has both an adapter contract and implementation runbook, while code and execution evidence remain absent.

Current-state evidence:

- The runbook and machine-readable implementation plan are documentation/data artifacts only.
- No production code, test file, validation command, endpoint probe, provider call, benchmark run, or package build was executed in this update.

## Capability: Dry-run preflight command deck

Capability id: `dry_run_preflight_command_deck`

Primary files:

- `C:\dev\local-model\benchmarks\dry-run-preflight-command-deck-v1.json`
- `C:\dev\local-model\project-docs\records\DRY-RUN-PREFLIGHT-COMMAND-DECK-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md`

What exists:

- Adds a machine-readable and human-readable command deck for dry-run and metadata-preflight execution.
- Separates commands into `metadata_only`, `requires_validation_approval`, and `requires_provider_endpoint_approval`.
- Lists exact commands for closed-loop dry plan, benchmark execution matrix, benchmark profile, context inventory, tool readiness, tool hardening, endpoint profiles, gather readiness, and Index fallback receipts.
- Lists future validation and endpoint/provider commands without authorizing or executing them.
- Raises the roadmap estimate to approximately `66%` because the roadmap now has a concrete execution deck, while actual execution evidence remains absent.

Current-state evidence:

- The command deck is a documentation/data artifact only.
- Input path checks confirmed the referenced current scripts and benchmark data artifacts exist before the deck was created.
- No command in the deck was executed in this update.
- No validation command, endpoint probe, provider call, benchmark run, or package build was executed in this update.

## Capability: Cross-harness adapter contract

Capability id: `cross_harness_adapter_contract`

Primary files:

- `C:\dev\local-model\benchmarks\cross-harness-adapter-contract-v1.json`
- `C:\dev\local-model\project-docs\records\CROSS-HARNESS-ADAPTER-CONTRACT-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\CODEX-FLYWHEEL-BENCHMARK-COMPARISON-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Defines a non-executing contract for comparable task execution across Codex harness, Flywheel harness, Claude Code, OpenCode, local 14B, local 32B, and dry/null providers.
- Defines planned schemas `harness.cross-harness-task-scorecard/v1` and `harness.cross-harness-run-receipt/v1`.
- Defines per-provider roles, current evidence, allowed modes, required receipts, scorecard row fields, comparability checks, and artifact layout.
- Updates benchmark methodology and Codex-vs-Flywheel comparison status so future comparisons require task id, prompt hash, metric schema, execution mode, provider role, and receipt compatibility.
- Keeps the roadmap estimate at approximately `66%` while making the comparison contract more concrete.

Current-state evidence:

- Targeted checks observed `C:\dev\local-model\harness.cmd`, `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`, `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`, `C:\Users\Zain\AppData\Local\Programs\@opencode-aidesktop`, and `E:\local-model-run`.
- `index.index_context_envelope` still returned `Transport closed` in this update.
- No provider adapter, provider call, endpoint probe, benchmark run, validation command, or package build was executed in this update.

## Capability: 14B/32B release scaffold pack

Capability id: `local_model_release_scaffold_pack`

Primary files:

- `C:\dev\local-model\project-docs\releases\14B\MODEL_CARD.md`
- `C:\dev\local-model\project-docs\releases\14B\README.md`
- `C:\dev\local-model\project-docs\releases\14B\PROVENANCE.md`
- `C:\dev\local-model\project-docs\releases\14B\CHECKSUMS.txt`
- `C:\dev\local-model\project-docs\releases\14B\ENDPOINTS.md`
- `C:\dev\local-model\project-docs\releases\14B\USAGE.md`
- `C:\dev\local-model\project-docs\releases\14B\BENCHMARKS.md`
- `C:\dev\local-model\project-docs\releases\14B\SAFETY-ACCOUNTABILITY.md`
- `C:\dev\local-model\project-docs\releases\14B\RELEASE-CHECKLIST.md`
- `C:\dev\local-model\project-docs\releases\32B\MODEL_CARD.md`
- `C:\dev\local-model\project-docs\releases\32B\README.md`
- `C:\dev\local-model\project-docs\releases\32B\PROVENANCE.md`
- `C:\dev\local-model\project-docs\releases\32B\CHECKSUMS.txt`
- `C:\dev\local-model\project-docs\releases\32B\ENDPOINTS.md`
- `C:\dev\local-model\project-docs\releases\32B\USAGE.md`
- `C:\dev\local-model\project-docs\releases\32B\BENCHMARKS.md`
- `C:\dev\local-model\project-docs\releases\32B\SAFETY-ACCOUNTABILITY.md`
- `C:\dev\local-model\project-docs\releases\32B\RELEASE-CHECKLIST.md`
- `C:\dev\local-model\project-docs\records\MODEL-NAMING-PUBLISHING-PLAN-14B-32B-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Adds draft release scaffolds for the 14B and 32B local model tracks.
- Uses working names `Flywheel-Local-Coder-14B` and `Flywheel-Local-Coder-32B`.
- Creates model-card, README, provenance, checksum, endpoint, usage, benchmark, safety/accountability, and release-checklist files for each track.
- Marks all unproven release gates as `missing_evidence` and keeps both model tracks blocked from publication.
- Raises the roadmap estimate to approximately `68%` because the release artifact layout now exists, while model evidence remains absent.

Current-state evidence:

- The release scaffolds are documentation templates only.
- `E:\local-model-run` root existence was previously observed, but model-specific file inventory, endpoint health, benchmark quality, checksums, provenance, license compatibility, and publish approval are not verified here.
- No model weights were read, no checksums were computed, no endpoint was probed, no benchmark was run, no validation command was executed, and no publication action was taken in this update.

## Capability: Closed-loop integration schematic and objective evidence matrix

Capability id: `closed_loop_integration_schematic_evidence_matrix`

Primary files:

- `C:\dev\local-model\project-docs\schematics\closed-loop-integration.graph.json`
- `C:\dev\local-model\project-docs\records\CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md`
- `C:\dev\local-model\project-docs\records\OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.json`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Adds a machine-readable closed-loop graph with schema `harness.closed-loop-integration-graph/v1`.
- Maps Codex harness, Flywheel harness, Claude Code, OpenCode, local 14B/32B, Index, Forum, Gather, Crucible, Telos, mneme, relay, plexus, benchmark contracts, endpoint profiles/gates, release gates, closed-loop seed, receipt store, comparison, outcome synthesis, and the Forum deep-verify benchmark lane.
- Labels each node as observed, available, scaffolded, contract-only, degraded, needs discovery, needs adapter, release scaffold only, or requires approval.
- Adds explicit promotion gates for Index transport, metadata preflights, agentic manifest generation, cross-harness adapters, endpoint health, shared benchmark execution, Forum ledger scaling, enterprise readiness, model release, and experimental outcome.
- Adds a machine-readable and human-readable objective evidence matrix mapping the active objective to current evidence, missing proof, and next gates.
- Updates the roadmap estimate from approximately `68%` to approximately `69%` because the control/evidence layer is more explicit, while execution evidence remains missing.

Current-state evidence:

- The referenced objective file was read from `C:\Users\Zain\.codex\attachments\7a657b2a-776e-435b-bd23-750af5d91e7b\pasted-text-1.txt`.
- `forum.route` returned a model-foundry validation architecture frame for this update.
- `index.index_context_envelope` returned `Transport closed` for `C:\dev` in this update and remains a degraded integration risk.
- Existing roadmap and benchmark contract artifacts were observed under `C:\dev\local-model`.
- No tests, benchmarks, endpoint probes, provider calls, model weight reads, package builds, or validation commands were run in this update.

Known gaps:

- The schematic is hand-authored from current artifacts; no generator or drift check keeps it synchronized yet.
- The evidence matrix is a control artifact, not proof that the requirements are complete.
- Forum route observations were not persisted into the harness file-backed store in this update.
- Index MCP degradation still needs repair or a fresh fallback receipt before any context map can be treated as current.

Next promotion step:

- Run and validate the non-executing agentic task-set manifest generator and add a schematic drift/generator path so benchmark contracts, planned artifacts, and graph nodes stay synchronized before provider execution.

## Capability: Agentic task-set manifest generator

Capability id: `agentic_task_set_manifest_generator`

Primary files:

- `C:\dev\local-model\harness\agentic_task_manifest.py`
- `C:\dev\local-model\scripts\run_agentic_task_set_manifest.py`
- `C:\dev\local-model\tests\test_agentic_task_set_manifest.py`
- `C:\dev\local-model\scripts\run_harness_cli.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`
- `C:\dev\local-model\benchmarks\agentic-task-set-adapter-v1.json`
- `C:\dev\local-model\benchmarks\dry-run-preflight-command-deck-v1.json`
- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md`
- `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md`

What exists:

- Implements schema `harness.agentic-task-manifest/v1`.
- Reads the custom agentic task set and adapter contract.
- Validates required task-set, adapter, and task fields.
- Expands each task into stable prompt text and `raw_prompt_sha256`.
- Maps every task to its adapter-defined benchmark id.
- Emits coverage units, dataset lanes, benchmark ids, metric weights, planned artifact paths, and non-execution guards.
- Emits manifest-only `harness.agentic-task-scorecard/v1` rows for configured provider roles, defaulting to `dry`.
- Marks every scorecard row as `status=planned`, `execution_mode=manifest_only`, and `failure_class=not_executed`.
- Adds `harness.cmd agentic-tasks` front-controller wiring.
- Adds the agentic task manifest as a metadata preflight in the closed-loop seed with `--skip-agentic-task-manifest`.
- Updates the dry-run command deck so the manifest command is metadata-only rather than future-only.

Current-state evidence:

- Source files and tests were added or updated in this slice.
- The manifest generator is intentionally non-executing and does not call providers, probe endpoints, read model weights, run benchmarks, or claim task success.
- `forum.route` routed this work to the model-foundry validation/architecture frame.
- `index.index_context_envelope` still returned `Transport closed`; Index remains a degraded dependency.
- No tests, benchmarks, endpoint probes, provider calls, model weight reads, package builds, or validation commands were run in this update.

Known gaps:

- The manifest generator has not been executed in this session.
- Targeted tests have been added but not run.
- Benchmark coverage and outcome synthesis do not yet deeply score `harness.agentic-task-scorecard/v1` beyond planned artifact linkage.
- Provider-specific adapters still need dry/null rows and later executed scorecard import.

Next promotion step:

- Run targeted validation when approved, then generate the first `agentic_task_manifest.json` receipt and teach benchmark coverage/outcome to treat manifest-only rows as planned coverage rather than benchmark evidence.

## 2026-07-09 update: planned-only benchmark intent ingestion

- `scripts/run_benchmark_profile_coverage.py` recognizes `harness.agentic-task-manifest/v1` artifacts as planned-only coverage. Planned manifests report benchmark ids, units, provider roles, and dataset lanes but do not count as observed benchmark evidence.
- `scripts/run_closed_loop_outcome_report.py` now exposes `agentic_task_manifest_signals` separately from scorecard signals so planned agentic tasks cannot inflate executed benchmark counts.
- Added `benchmarks/forum-ledger-deep-verify-scaling-v1.json` for forum ledger `verify(deep=True)` scaling pressure. Required measurements include shallow/deep verify latency, entries/sec, payload bytes/sec, peak RSS, JSONL size, checkpoint time, causal-chain latency, redaction mix, tamper index, and crash-recovery verdict.

## 2026-07-09 update: Index resilience + Boris realtime multimodal lane

- Index MCP hardening: `C:/dev/public/index/src/index_graph/mcp.py` now serializes tool failures, including `SystemExit`, as `index.mcp-tool-error/v1` JSON payloads. `C:/dev/public/index/src/index_graph/scan.py` now skips unreadable directories during discovery rather than aborting the walk.
- Forum scaling benchmark: `forum_ledger_deep_verify_scaling` is now declared in the benchmark profile and recognized by coverage/outcome synthesis through schema `forum.deep-verify-benchmark/v1`.
- Embodied realtime multimodal benchmark: added `C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json`, benchmark id `embodied_realtime_multimodal_pressure`, and task `agt-013-embodied-realtime-multimodal` for robotics latency, sensor grounding, code-drawing visual repair, and affective drift probes.
- Evidence status: implementation/contracts only. Tests, Index MCP retest, model-card verification, and benchmark execution remain pending.

## 2026-07-09 update: embodied realtime multimodal command

- New command: `harness.cmd embodied-realtime`.
- Delegates to `scripts/run_embodied_realtime_multimodal_plan.py`.
- Output schema: `harness.embodied-realtime-multimodal/v1`.
- Evidence posture: metadata-only planned probes and dry scorecard rows. Rows are marked `not_executed` and must not be used as executed benchmark quality evidence.
- Coverage/outcome support: benchmark coverage treats the artifact as planned-only; closed-loop outcome extracts `embodied_realtime_signals` with provider roles, latency budgets, dataset lanes, pressure variables, probe ids, coverage units, and unverified model leads.

## 2026-07-09 update: embodied realtime closed-loop wiring

- `scripts/run_closed_loop_benchmark_seed.py` now emits `embodied_realtime_multimodal_plan.json` and `.md` by default as a metadata-only preflight step.
- The new seed skip flag is `--skip-embodied-realtime`.
- `scripts/run_benchmark_execution_matrix.py` now declares dry-tier step `embodied_realtime_plan` with expected schema `harness.embodied-realtime-multimodal/v1`.
- Benchmark coverage inputs now include `embodied_realtime_multimodal_plan.json`, preserving planned coverage visibility without counting it as executed benchmark evidence.
- Evidence status: implementation only. Tests, seed dry plan execution, model-card verification, rendering checks, endpoint probes, and benchmark runs were not executed in this update.

## 2026-07-09 update: cross-harness manifest generator

- New module: `C:/dev/local-model/harness/cross_harness_manifest.py`.
- New command: `C:/dev/local-model/scripts/run_cross_harness_manifest.py`.
- New executable wrapper: `harness.cmd cross-harness`.
- Output schemas: `harness.cross-harness-manifest/v1` and planned `harness.cross-harness-task-scorecard/v1`.
- Closed-loop seed now includes `cross_harness_manifest` by default with `--skip-cross-harness-manifest`.
- Benchmark execution matrix now includes dry-tier `cross_harness_manifest`.
- Benchmark coverage and closed-loop outcome now ingest cross-harness manifests as planned-only evidence.
- Evidence status: implementation only. Tests, dry-plan generation, provider execution, endpoint probes, and benchmark runs were not executed in this update.

## 2026-07-09 update: current dry-run preflight command deck

- `C:/dev/local-model/benchmarks/dry-run-preflight-command-deck-v1.json` now includes current metadata-only commands for `run_agentic_task_set_manifest.py`, `run_cross_harness_manifest.py`, and `run_embodied_realtime_multimodal_plan.py`.
- `C:/dev/local-model/project-docs/records/DRY-RUN-PREFLIGHT-COMMAND-DECK-2026-07-09.md` now mirrors those commands.
- The deck no longer states that the agentic manifest command is unimplemented.
- The validation command remains approval-gated and now includes cross-harness, embodied realtime, execution matrix, seed, coverage, and outcome tests.
- Evidence status: documentation and command contract only. The deck, tests, metadata commands, provider calls, endpoint probes, and benchmarks were not executed in this update.

## 2026-07-09 update: schematic drift maintenance

- New module: `C:/dev/local-model/harness/schematic_drift.py`.
- New command: `C:/dev/local-model/scripts/run_schematic_drift_check.py`.
- New executable wrapper: `harness.cmd schematic-drift`.
- Output schema: `harness.schematic-drift-check/v1`.
- Closed-loop seed now includes `schematic_drift_check` by default with `--skip-schematic-drift`.
- Benchmark execution matrix now includes dry-tier `schematic_drift_check`.
- Closed-loop outcome now ingests schematic drift receipts under `schematic_drift_signals`.
- The closed-loop integration graph and schematic report now include cross-harness manifest, embodied realtime plan, and schematic drift surfaces.
- Evidence status: implementation only. Tests, drift command execution, metadata artifact generation, provider calls, endpoint probes, and benchmark runs were not executed in this update.

## 2026-07-09 update: adapter runtime matrix

- New module: `C:/dev/local-model/harness/adapter_runtime_matrix.py`.
- New command: `C:/dev/local-model/scripts/run_adapter_runtime_matrix.py`.
- New executable wrapper: `harness.cmd adapter-runtime`.
- Output schema: `harness.adapter-runtime-matrix/v1`.
- Purpose: join the cross-harness adapter contract with endpoint profile metadata and optional endpoint auth metadata so Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null readiness is visible before execution.
- Closed-loop seed now includes `adapter_runtime_matrix` by default with `--skip-adapter-runtime-matrix`.
- Benchmark execution matrix now includes dry-tier `adapter_runtime_matrix`.
- Benchmark coverage recognizes adapter runtime matrices as planned-only cross-harness evidence.
- Closed-loop outcome exposes adapter readiness under `adapter_runtime_signals`, including manifest-ready roles, focused-run-ready roles, endpoint-profile-ready roles, auth-ready roles, and blocking gate counts.
- The closed-loop schematic graph and schematic drift checker now treat `adapter_runtime_matrix` as a required node.
- Evidence status: implementation only. Tests, metadata artifact generation, endpoint probes, provider calls, token-store reads, model-weight reads, and benchmark runs were not executed in this update.

## Capability: Forum route receipt observability

Capability id: `forum_route_receipts`

- New command: `C:/dev/local-model/scripts/run_forum_route_receipts.py`.
- New executable wrapper: `harness.cmd forum-route`.
- New tests: `C:/dev/local-model/tests/test_forum_route_receipts.py`.
- Output schema: `harness.forum-route-receipts/v1`.
- Purpose: turn `forum.route` decisions into auditable closed-loop metadata by storing route prompt hashes, optional observed route-frame confidence, escalation status, domain, intent, posture, proof lane, domain lane, and human contract.
- Closed-loop seed now includes `forum_route_receipts` by default immediately after endpoint/account-lane posture, with `--skip-forum-route-receipts` and repeatable `--forum-route-text`.
- Closed-loop outcome exposes route observability under `forum_route_signals`, including route count, observed route frames, route-text-only rows, escalation count, mean observed confidence, decided agents, domains, intents, and proof lanes.
- The dry-run command deck includes a metadata-only route receipt command for the observed low-confidence `forum.route` call in this slice.
- Evidence status: implementation only. Tests, metadata artifact generation, provider calls, endpoint probes, and benchmark runs were not executed in this update.

## Capability: MCP tool health receipts

Capability id: `mcp_tool_health_receipts`

- New command: `C:/dev/local-model/scripts/run_mcp_tool_health_receipts.py`.
- New executable wrapper: `harness.cmd mcp-health`.
- New tests: `C:/dev/local-model/tests/test_mcp_tool_health_receipts.py`.
- Output schema: `harness.mcp-tool-health/v1`.
- Purpose: record configured flagship tool roots and injected non-secret status observations for `index`, `forum`, `telos`, `gather`, `crucible`, `aleph`, `mneme`, `relay`, `plexus`, and `local-model`.
- Closed-loop seed now includes `mcp_tool_health` by default immediately after Forum route receipts, with `--skip-mcp-tool-health`, `--mcp-tool-health-tools`, and repeatable `--mcp-tool-health-observation`.
- Closed-loop outcome exposes tool health under `mcp_tool_health_signals`, including observed tools, existing roots, healthy observed tools, degraded observed tools, configured-unobserved tools, missing roots, verdict counts, healthy tools, degraded tools, and unobserved tools.
- The dry-run command deck includes metadata-only observations from this slice: `index=TRANSPORT_CLOSED`, `forum=MATCH`, and `telos=MATCH`.
- The closed-loop integration schematic and schematic drift checker now require `forum_route_receipts` and `mcp_tool_health` nodes and edges into `closed_loop_seed`.
- Evidence status: implementation only. Tests, metadata artifact generation, endpoint probes, provider calls, token-store reads, model-weight reads, and benchmark runs were not executed in this update.
