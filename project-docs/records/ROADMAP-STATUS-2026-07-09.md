# Codex/Flywheel Local-Model Harness Roadmap Status

Date: 2026-07-09

Status type: evidence-backed planning status, not a benchmark result.

## Evidence standard

This status record separates observed local evidence from incomplete work. It does not claim that tests, probes, endpoint checks, or benchmarks passed. Validation and benchmark execution still require an explicit execution pass.

Observed evidence used for this status:

- `C:\dev\local-model\project-docs\INFRASTRUCTURE.md` documents reproducible commands for context inventory, tool readiness, tool hardening, model release readiness, model publish planning, endpoint profiles, endpoint gates, gather readiness, benchmark profile, benchmark coverage, benchmark execution matrix, harness comparison, closed-loop seed, and outcome synthesis.
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py` now includes child steps for Forum route receipts, MCP tool health receipts, benchmark execution matrix, benchmark profile, context inventory, expanded tool readiness, tool hardening, endpoint profiles, endpoint gates, model release readiness, model publish plan, gather readiness, benchmark coverage, and harness comparison.
- `C:\dev\local-model\project-docs\records\CAPABILITY-CATALOG-2026-07-09.md` records multiple capabilities as added or updated, while repeatedly noting that runtime validation was not run in this slice.
- The live `index` MCP context envelope is currently degraded in this session with `Transport closed`; the local Index receipt fallback is documented as the current mitigation.
- `C:\dev\local-model\project-docs\schematics\closed-loop-integration.graph.json` now maps the closed-loop integration graph with explicit observed, scaffolded, degraded, and missing-evidence nodes.
- `C:\dev\local-model\project-docs\records\OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md` now tracks the active objective requirement-by-requirement against evidence, missing proof, and next gates.
- `C:\dev\local-model\scripts\run_agentic_task_set_manifest.py` now implements the non-executing custom agentic task manifest generator with prompt hashes, planned artifact paths, and manifest-only dry scorecard rows.
- `C:\tmp\forum_route_receipts_20260709_current.json`, `C:\tmp\mcp_tool_health_20260709_current.json`, `C:\tmp\tool_readiness_20260709_current.json`, and `C:\tmp\harness_closed_loop_seed_plan_20260709_current.json` were produced through `C:\dev\local-model\harness.cmd` as metadata preflight artifacts.
- Focused seed `run_20260709T150956_4b913c32efa2` produced `C:\tmp\harness_closed_loop_seed_focused_postfix_20260709.json`; follow-up classifier retry produced `C:\tmp\classifier_friction_postfix_retry_20260709.json`; coverage and comparison refreshes produced `C:\tmp\benchmark_profile_coverage_postfix_retry_20260709.json` and `C:\tmp\harness_comparison_report_postfix_retry_20260709.json`.
- Endpoint profile/gate refresh `run_20260709_endpoint32b_integrated` produced `C:\tmp\model_endpoint_profiles_32b_integrated_20260709.json`, `C:\tmp\model_endpoint_gate_32b_integrated_20260709.json`, and `C:\tmp\local_model_launch_readiness_32b_integrated_20260709.json`.

## Roadmap progress estimate

Scoring method: each workstream is rated from `0` to `4`.

- `0`: not started.
- `1`: located or sketched.
- `2`: scaffolded and integrated into commands/docs.
- `3`: executed with durable artifacts.
- `4`: validated, benchmarked, documented, and release-ready.

Overall estimate: `25 / 32`, approximately `78%`.

This is a planning estimate, not a performance metric.

| Workstream | Stage | Status | Evidence | Missing gate |
| --- | ---: | --- | --- | --- |
| Tool and infrastructure integration | 2.5 / 4 | Preflight-integrated, live execution incomplete | Closed-loop seed includes Forum route receipts, MCP tool health receipts, context inventory, expanded tool readiness, hardening, gather readiness, Index fallback, and comparison steps. Current preflight artifacts show 11 configured roots, 0 missing roots, `forum`/`telos` healthy, and `index` degraded with `transport_closed`. | Stable `index` MCP transport, live tool-specific connectivity proof, and full seed receipts. |
| Harness comparison and benchmark evidence | 3 / 4 | Focused Codex/local seed artifacts exist, full comparison incomplete | Focused seed, classifier retry, coverage, and comparison artifacts exist. Classifier retry shows `accountability_first` outperforming guardrail modes for Codex on one task. Comparison remains insufficient because no same-key Codex/Flywheel rows exist. | Run same-key Codex/Flywheel rows, Claude Code/OpenCode rows, forum ledger scaling, and broader task battery. |
| Local model endpoint and agentic workflow support | 2.85 / 4 | 32B model reference integrated; launch-readiness now identifies the live port blocker | Gate artifact `C:\tmp\model_endpoint_gate_32b_integrated_20260709.json` reports `14B` serve health/generation ok with expected model ref. Launch-readiness artifact `C:\tmp\local_model_launch_readiness_32b_integrated_20260709.json` reports `14B` as `candidate_running_gate_required` on `8765` and `32B` as `port_conflict_wrong_service` on `8767`, owned by a generic `python -m http.server`. | Free or override the `32B` serve port, start a real 32B `harness/serve.py`, then rerun endpoint gate and agentic local benchmark rows. |
| Executable harness packaging | 2.5 / 4 | CLI/front-controller path produced preflight artifacts | Infrastructure and catalog records include executable harness commands and schema/report surfaces; `harness.cmd` produced route, MCP health, tool readiness, and dry plan artifacts. | Full packaged executable release, install verification, and local model configuration proof. |
| mneme, relay, and plexus enterprise readiness | 2 / 4 | Readiness and hardening plan path exists | Tool readiness and tool hardening commands are documented and wired into closed-loop seed. | Shipped tool changes, CI/package/docs readiness, and competitive feature proof. |
| 14B and 32B release track | 2 / 4 | Release-readiness and publish-plan path exists | Model release readiness and model publish plan commands are documented and wired into closed-loop seed. | Model names, model cards, checksums, benchmark evidence, provenance/licensing notes, and publish approval. |
| Experimental outcome and recursive loop | 2.75 / 4 | Partial outcome exists from focused seed | `OUTCOME_PARTIAL` and classifier retry artifacts exist, with limitations and next actions recorded. | Produce complete same-key comparison outcome from Codex/Flywheel/Claude Code/OpenCode/local rows. |
| Capability catalog and documentation | 3.25 / 4 | Catalog is actively maintained and now has an integration schematic plus objective evidence matrix | Capability catalog records the benchmark execution matrix, closed-loop seed, outcome synthesis, endpoint/readiness/publish, fallback capabilities, closed-loop schematic, and objective evidence matrix. | Validation pass, generated artifacts, schematic drift check, and final release documentation pack. |

## Required final outputs audit

| Required output | Current status | Evidence state | Next evidence gate |
| --- | --- | --- | --- |
| Workspace context map | Drafted | `C:\dev\local-model\project-docs\records\WORKSPACE-CONTEXT-MAP-2026-07-09.md` records observed roots and next context gates. | Execute context inventory and preserve JSON/Markdown artifacts. |
| Tool integration report | Drafted | `C:\dev\local-model\project-docs\records\TOOL-INTEGRATION-REPORT-2026-07-09.md` records observed roots, integration surfaces, and missing gates. | Execute readiness/hardening against current `C:\dev` tool roots. |
| Harness architecture and endpoint report | Drafted | `C:\dev\local-model\project-docs\records\HARNESS-ARCHITECTURE-ENDPOINT-REPORT-2026-07-09.md` records executable, benchmark, endpoint, and release surfaces. | Execute endpoint profile/gate for 14B/32B and configured provider endpoints. |
| Benchmark methodology | Drafted-plus | `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md` defines provider roles, metrics, lanes, tiers, validity rules, and references the custom task corpus plus adapter contract. | Implement the manifest adapter, run dry plan, then focused benchmark seed, then coverage report. |
| Codex vs Flywheel benchmark comparison | Drafted, no result | `C:\dev\local-model\project-docs\records\CODEX-FLYWHEEL-BENCHMARK-COMPARISON-2026-07-09.md` defines the comparison shape and missing evidence. | Run the same task set through both harnesses and synthesize deltas. |
| Local model benchmark summary | Drafted, no result | `C:\dev\local-model\project-docs\records\LOCAL-MODEL-BENCHMARK-SUMMARY-2026-07-09.md` records local model benchmark gates. | Run local endpoint and agentic benchmark lanes. |
| mneme readiness report and shipped changes | Drafted, no shipped changes | `C:\dev\local-model\project-docs\records\MNEME-READINESS-REPORT-2026-07-09.md` records the readiness gate. | Execute readiness, implement high-priority gaps, and record shipped changes. |
| relay readiness report and shipped changes | Drafted, no shipped changes | `C:\dev\local-model\project-docs\records\RELAY-READINESS-REPORT-2026-07-09.md` records the readiness gate. | Execute readiness, implement high-priority gaps, and record shipped changes. |
| plexus readiness report and shipped changes | Drafted, no shipped changes | `C:\dev\local-model\project-docs\records\PLEXUS-READINESS-REPORT-2026-07-09.md` records the readiness gate. | Execute readiness, implement high-priority gaps, and record shipped changes. |
| 14B/32B naming and publishing plan | Drafted-plus | `C:\dev\local-model\project-docs\records\MODEL-NAMING-PUBLISHING-PLAN-14B-32B-2026-07-09.md` records working names and do-not-publish gates; draft release scaffolds exist under `C:\dev\local-model\project-docs\releases\14B` and `C:\dev\local-model\project-docs\releases\32B`. | Execute release readiness, fill model cards/checklists with artifact evidence, and block publish until gates pass. |
| Experimental outcome document | Drafted, no result | `C:\dev\local-model\project-docs\records\EXPERIMENTAL-OUTCOME-2026-07-09.md` records the hypothesis and missing evidence. | Generate outcome from actual shared-run artifacts. |
| Capability catalog updates | Ongoing | Catalog exists and has been updated as work lands. | Keep appending verified capability records and validation status. |
| Next recursive improvement loop | Drafted | `C:\dev\local-model\project-docs\records\NEXT-RECURSIVE-IMPROVEMENT-LOOP-2026-07-09.md` defines the next evidence-producing loop. | Execute one focused loop and update this record with artifact paths. |

## Additional control artifacts

| Control artifact | Current status | Evidence state | Next evidence gate |
| --- | --- | --- | --- |
| Closed-loop integration schematic | Created, not executed | `C:\dev\local-model\project-docs\schematics\closed-loop-integration.graph.json` and `C:\dev\local-model\project-docs\records\CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md` map the current closed-loop graph and promotion gates. | Add generator/drift check and tie graph nodes to receipt-producing commands. |
| Objective evidence matrix | Created, partial evidence | `C:\dev\local-model\project-docs\records\OBJECTIVE-EVIDENCE-MATRIX-2026-07-09.md` and `.json` map requirements to evidence, missing proof, and next gates. | Use the matrix as the completion audit checklist after executing metadata, endpoint, provider, and release gates. |

## Immediate next gates

1. Free or override the `32B` serve port; current `8767` owner is a generic `python -m http.server`, not `harness/serve.py`.
2. Run same-key Codex-vs-Flywheel rows so `COMPARISON_INSUFFICIENT` can become a real delta.
3. Add Claude Code and OpenCode executable rows after adapter discovery gates are satisfied.
4. Run hardening preflights and implement one bounded mneme/relay/plexus enterprise slice.
5. Add and run the forum replayable-ledger deep-verify scaling benchmark before making public performance claims about large content-addressed ledgers.
6. Rerun the focused seed with the classifier timeout aligned to observed Codex latency, or keep classifier as a separate long-running artifact.
7. Run endpoint profiles and gates for 14B/32B only after local endpoint configuration is confirmed.
8. Generate the closed-loop outcome from the shared run store.
9. Add and run the forum replayable-ledger deep-verify scaling benchmark before making public performance claims about large content-addressed ledgers.

## Risks

- `index` MCP transport instability is still an active integration risk. The local fallback improves resilience but does not prove the MCP path is healthy.
- Most current progress is infrastructure and measurement readiness, not measured benchmark improvement.
- The roadmap cannot honestly move beyond roughly halfway until real shared-task benchmark artifacts exist.
- Enterprise readiness for mneme, relay, and plexus remains mostly a planned hardening lane until shipped changes and validation artifacts exist.
- Forum's causal-ledger design has functional verification evidence, but deep verification scaling is not yet measured in this roadmap.

## 2026-07-09 update: planned task coverage and forum deep-verify scaling

- Added planned-only ingestion for `harness.agentic-task-manifest/v1` in benchmark coverage and closed-loop outcome synthesis. These artifacts now surface planned benchmark ids, coverage units, provider roles, and dataset lanes without increasing executed benchmark coverage or scorecard counts.
- Added benchmark contract `C:/dev/local-model/benchmarks/forum-ledger-deep-verify-scaling-v1.json` to turn forum feedback on `verify(deep=True)` into measurable scale pressure: entry count, payload bytes, redaction ratio, crash recovery, parent-chain depth, and checkpoint interval.
- Status: implemented, not validated, not run. Roadmap estimate moves to `22.75 / 32` units, approximately `71%`, because the reporting loop now distinguishes planned intent from executed evidence for the agentic task set.

## 2026-07-09 update: Index transport containment and embodied realtime benchmark lane

- Patched `C:/dev/public/index` MCP failure handling so `SystemExit` and other tool-call failures return `index.mcp-tool-error/v1` payloads with `UNVERIFIABLE` status instead of terminating the stdio process where Python can contain the failure.
- Patched Index repository discovery to use an `os.walk` error hook and Unicode-safe warnings, reducing large-workspace scan fragility around unreadable paths and non-UTF/console-hostile names.
- Promoted `forum_ledger_deep_verify_scaling` into the harness benchmark profile, coverage mapping, and closed-loop outcome signal extraction.
- Converted Boris/ENBSeries feedback into `embodied_realtime_multimodal_pressure`, a planned benchmark lane for tiny/realtime robotics-style models, synthetic sensor streams, code-drawn visual reasoning, simplified multimodal projections, and affective possessiveness/dominance drift.
- Status: implemented, not validated, not run. Roadmap estimate moves to `23.25 / 32` units, approximately `73%`, because benchmark scope and Index resilience improved but no execution evidence was produced in this step.

## 2026-07-09 update: embodied realtime multimodal plan command

- Added `scripts/run_embodied_realtime_multimodal_plan.py`, a metadata-only runner for `harness.embodied-realtime-multimodal/v1` artifacts. It expands the embodied realtime contract into provider-role x latency-budget x probe rows, prompt hashes, expected artifact paths, and dry scorecard rows with `failure_class=not_executed`.
- Added `harness.cmd embodied-realtime` to the executable front controller and manifest/registry surface. The command delegates to the metadata runner and does not call models, endpoints, sensors, renderers, or model-card sources.
- Added coverage and outcome ingestion for embodied realtime artifacts as planned-only evidence, separate from executed scorecards.
- Status: implemented, not validated, not run. Roadmap estimate moves to `23.5 / 32` units, approximately `73%`; this improves benchmark reproducibility and harness packaging but does not satisfy benchmark execution evidence.

## 2026-07-09 update: embodied realtime closed-loop wiring

- Added the embodied realtime multimodal plan as a default closed-loop seed preflight step after `agentic_task_manifest`, with `--skip-embodied-realtime` for already-receipted runs.
- Added dry-tier `embodied_realtime_plan` to the benchmark execution matrix, including expected schema `harness.embodied-realtime-multimodal/v1` and evidence gates for planned probe rows, non-executed dry scorecards, and unverified model leads.
- Added `embodied_realtime_multimodal_plan.json` to benchmark coverage artifact inputs so coverage/outcome can see the lane without granting executed benchmark credit.
- Live `forum.route` remained available but routed this slice as low-confidence evidence/investigation escalation; live `index.index_context_envelope` still returned `Transport closed`.
- Status: implemented, not validated, not run. Roadmap estimate moves to `23.75 / 32` units, approximately `74%`; orchestration coverage improved, but the main missing proof remains actual metadata artifacts, model-card verification, endpoint probes, rendered assertions, and shared provider scorecards.

## 2026-07-09 update: cross-harness manifest generator

- Added a non-executing cross-harness manifest generator for `harness.cross-harness-manifest/v1` and planned `harness.cross-harness-task-scorecard/v1` rows.
- Added `harness.cmd cross-harness`, closed-loop seed preflight `cross_harness_manifest`, dry-tier execution-matrix step `cross_harness_manifest`, benchmark coverage planned-only ingestion, and outcome `cross_harness_manifest_signals`.
- The manifest preserves same-task prompt hashes and provider-role receipt expectations for Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null roles without running providers.
- Live `forum.route` was available but low-confidence/escalated; live `index.index_context_envelope` still returned `Transport closed`.
- Status: implemented, not validated, not run. Roadmap estimate moves to `24 / 32` units, approximately `75%`; comparability planning improved, but executed same-task benchmark evidence is still missing.

## 2026-07-09 update: dry-run command deck refresh

- Updated `C:/dev/local-model/benchmarks/dry-run-preflight-command-deck-v1.json` and the matching command-deck record so agentic task manifest, cross-harness manifest, and embodied realtime plan are listed as current metadata-only preflights rather than future-only work.
- Updated the targeted validation command to include cross-harness, embodied realtime, execution matrix, seed, coverage, and outcome slices while keeping validation approval-gated.
- Updated the harness executable manifest test expectation to include `cross-harness`.
- Status: implemented, not validated, not run. Roadmap estimate moves to `24.25 / 32` units, approximately `76%`; the reproducible preflight surface is more accurate, but no command deck, tests, metadata artifacts, providers, endpoints, or benchmarks were executed.

## 2026-07-09 update: schematic drift maintenance surface

- Added `harness.schematic-drift-check/v1` metadata-only drift checking for required graph nodes, required graph edges, referenced local files, and stale prose markers.
- Added `scripts/run_schematic_drift_check.py`, `harness.cmd schematic-drift`, closed-loop seed step `schematic_drift_check`, and dry-tier execution-matrix step `schematic_drift_check`.
- Updated `closed-loop-integration.graph.json` and the schematic report so cross-harness manifest, embodied realtime plan, and schematic drift check are represented explicitly.
- Added outcome parsing for schematic drift receipts under `schematic_drift_signals`.
- Status: implemented, not validated, not run. Roadmap estimate moves to `24.5 / 32` units, approximately `77%`; schematic maintenance improved, but no drift command, tests, metadata artifacts, providers, endpoints, or benchmarks were executed.

## 2026-07-09 update: adapter runtime matrix and schematic alignment

- Added `harness.adapter-runtime-matrix/v1` as a metadata-only compatibility matrix for Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null paths.
- Added `scripts/run_adapter_runtime_matrix.py`, `harness.cmd adapter-runtime`, closed-loop seed step `adapter_runtime_matrix`, dry-tier execution-matrix step `adapter_runtime_matrix`, benchmark coverage planned-only ingestion, and outcome `adapter_runtime_signals`.
- Updated the closed-loop schematic graph, schematic report, and schematic drift requirements so `adapter_runtime_matrix` is a required node with a required path into the benchmark execution matrix.
- Status: implemented, not validated, not run. Roadmap estimate moves to `25 / 32` units, approximately `78%`; cross-harness adapter readiness is more explicit, but provider calls, endpoint probes, metadata artifacts, tests, and benchmark execution remain unrun.

## 2026-07-09 update: Index fallback MCP observation metadata

- Added explicit MCP observation fields to `scripts/run_index_receipt.py` so Index fallback receipts can record the observed MCP tool, status, error code, and error summary before CLI fallback is used.
- Updated the dry-run command deck so the current `index_context_envelope` transport failure is represented as structured receipt metadata: `mcp_status=transport_closed`, `mcp_error_code=transport_closed`, and `mcp_error_summary="Transport closed"`.
- Status: implemented, not validated, not run. Roadmap estimate remains `25 / 32` units, approximately `78%`; observability improved, but Index MCP is still degraded until a live MCP call returns a healthy envelope or a structured tool-error payload.

## 2026-07-09 update: Forum route receipt surface

- Added `scripts/run_forum_route_receipts.py`, a metadata-only route evidence command that records route prompt hashes plus optional observed `forum.route` metadata such as confidence, escalation, domain, intent, posture, proof lane, and human contract.
- Wired `forum_route_receipts` into the default closed-loop seed immediately after endpoint/account-lane posture, with `--skip-forum-route-receipts` and repeatable `--forum-route-text` overrides.
- Updated the dry-run command deck and tool integration report so Forum route decisions can become auditable artifacts instead of chat-only routing context.
- Status: implemented, not validated, not run. Roadmap estimate moves to `25.25 / 32` units, approximately `79%`; route observability improved, but actual run-to-run route confidence drift remains unmeasured until metadata preflights execute.

## 2026-07-09 update: MCP tool health receipt surface

- Added `scripts/run_mcp_tool_health_receipts.py`, a metadata-only tool health command that records configured root posture plus optional non-secret live observations for `index`, `forum`, `telos`, `gather`, `crucible`, `aleph`, `mneme`, `relay`, `plexus`, and `local-model`.
- Wired `mcp_tool_health` into the default closed-loop seed after Forum route receipts, with `--skip-mcp-tool-health`, `--mcp-tool-health-tools`, and repeatable `--mcp-tool-health-observation`.
- Added outcome synthesis under `mcp_tool_health_signals`, including observed tools, healthy tools, degraded tools, configured-unobserved tools, missing roots, and verdict counts.
- Current observed metadata from this slice: `index=TRANSPORT_CLOSED`, `forum=MATCH`, and `telos=MATCH`.
- Status: implemented, not validated, not run. Roadmap estimate moves to `25.5 / 32` units, approximately `80%`; tool health observability improved, but no metadata artifact or validation run has been executed yet.

## 2026-07-09 update: executable route and MCP health preflights

- Added `harness.cmd forum-route` to the executable front controller and manifest/registry surface. It delegates to `scripts/run_forum_route_receipts.py`.
- Added `harness.cmd mcp-health` to the executable front controller and manifest/registry surface. It delegates to `scripts/run_mcp_tool_health_receipts.py`.
- Updated `tests/test_harness_cli.py` so command delegation and manifest listing cover both new metadata-only preflights.
- Status: implemented, not validated, not run. Roadmap estimate moves to `25.75 / 32` units, approximately `80%`; executable packaging coverage improved, but the harness manifest command and targeted tests have not been executed.
