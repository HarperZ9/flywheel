# Objective Evidence Matrix - Codex/Flywheel Local-Model Harness

Date: 2026-07-09

Status: partial evidence, no completion claim.

This matrix turns the active objective into explicit proof gates. It is not a benchmark result and does not claim that endpoints, providers, tests, or package builds passed.

## Execution boundary for this update

- Tests run: none.
- Benchmarks run: none.
- Endpoint probes run: none.
- Provider/model calls run: none.
- Model weights read: none.
- Metadata preflight artifacts run through `harness.cmd`: forum route receipts, MCP/tool health receipts, expanded tool readiness receipts, and dry closed-loop seed plan.
- Completion claim: none.

## Live tool signals

- `forum.route`: available. It returned a model-foundry validation architecture frame for this schematic/evidence task.
- `index.index_context_envelope`: degraded. It returned `Transport closed` for `C:\dev` in this update.

## Requirement matrix

| ID | Requirement | Current status | Evidence | Missing proof | Next gate |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Use Index to scan/map `C:\dev` before architectural assumptions. | Partial, degraded | `C:\dev\local-model\project-docs\records\ROADMAP-STATUS-2026-07-09.md` records the Index risk and fallback path. | Healthy live Index MCP envelope or fresh degraded fallback receipt. | Repair/run Index MCP, or generate a fresh fallback receipt with freshness status. |
| REQ-002 | Use Forum to route ambiguous/cross-domain work. | Receipted preflight | Live `forum.route` output in this update; `C:\tmp\forum_route_receipts_20260709_current.json`; `C:\dev\local-model\project-docs\schematics\closed-loop-integration.graph.json`. | Route receipts inside a full shared-run benchmark seed. | Carry forum route receipts into the focused seed run. |
| REQ-003 | Gather scratch/temp/mid-flight/Claude/Codex/OpenCode/prior benchmark context. | Scaffolded, not executed | `C:\dev\local-model\project-docs\records\WORKSPACE-CONTEXT-MAP-2026-07-09.md`; `C:\dev\local-model\benchmarks\dry-run-preflight-command-deck-v1.json`. | Fresh context inventory artifact covering all specified sources. | Run metadata-only context inventory after approval. |
| REQ-004 | Integrate existing tools before inventing replacements. | Preflight receipts produced | `C:\dev\local-model\project-docs\records\TOOL-INTEGRATION-REPORT-2026-07-09.md`; `C:\tmp\mcp_tool_health_20260709_current.json`; `C:\tmp\tool_readiness_20260709_current.json`; capability catalog. | End-to-end receipts from a full seed run and live tool-specific execution where safe. | Run focused seed and then hardening preflights. |
| REQ-005 | Benchmark `5.3-Codex-Spark` in Codex and Flywheel harnesses and compare. | Contract only | `C:\dev\local-model\benchmarks\cross-harness-adapter-contract-v1.json`. | Same-task executed scorecards for both harnesses. | Implement manifest/adapter generator, run dry rows, then focused provider rows after approval. |
| REQ-006 | Build serious custom agentic benchmarks. | Manifest generator implemented, not run | `C:\dev\local-model\benchmarks\agentic-task-set-v1.json`; adapter and cross-harness contracts; `C:\dev\local-model\scripts\run_agentic_task_set_manifest.py`. | Manifest execution artifact, scorecards, coverage, executed provider artifacts. | Run non-executing manifest generation and targeted validation after approval. |
| REQ-007 | Measure quality, completion, latency, cost/resource use, reliability, tool use, failure modes, reproducibility. | Metric contract only | `C:\dev\local-model\project-docs\records\BENCHMARK-METHODOLOGY-2026-07-09.md`. | Executed rows with metric values. | Run focused benchmark seed and coverage after metadata preflights. |
| REQ-008 | Verify local endpoints for 14B, 32B, and other local models. | Profile path only | Local model and endpoint reports. | Fresh endpoint profile and live endpoint gate artifacts. | Run endpoint profiles metadata-only, then endpoint gate after approval. |
| REQ-009 | Compile harness into full executable format and plug in local models. | Executable preflight proven | `C:\dev\local-model\harness.cmd`; `C:\tmp\harness_closed_loop_seed_plan_20260709_current.json`; architecture/endpoint report. | Packaged executable, install/run proof, local model config proof, and live endpoint gate artifacts. | Run focused seed through `harness.cmd`, then package validation after approval. |
| REQ-010 | Make mneme, relay, plexus enterprise-ready and shipped. | Readiness drafts only | Readiness reports for each tool. | Shipped code changes and validation evidence. | Run readiness receipts, implement one hardening slice per tool, validate after approval. |
| REQ-011 | Name and prepare 14B/32B for publication without publishing early. | Release scaffold only | Model naming plan and release scaffolds. | Weights inventory, checksums, provenance/licensing, benchmark results, publish approval. | Run model release readiness after endpoint and benchmark evidence exist. |
| REQ-012 | Produce required final outputs. | Draft pack exists | Roadmap status and capability catalog list the durable outputs. | Executed benchmark data and shipped-change evidence for draft outputs. | Drive closure from this matrix, not from chat-only status. |
| REQ-013 | Improve Forum causal-ledger benchmark rigor. | Implemented, not run | `C:\dev\public\forum\src\forum\bench_deep_verify.py`; CLI/docs updates. | Actual `forum.deep-verify-benchmark/v1` artifacts. | Run deep-verify profiles after validation/benchmark execution approval. |
| REQ-014 | Maintain schematics organically. | Schematic created | `C:\dev\local-model\project-docs\schematics\closed-loop-integration.graph.json`; schematic report. | Generator/drift check tied to code and benchmark receipts. | Add schematic generator/drift check after manifest adapter exists. |

## Current conclusion

The program has a stronger evidence boundary now, but it is still not complete. The main missing proof is execution evidence: focused benchmark seed artifacts, endpoint gates, same-task provider scorecards, Forum deep-verify scaling artifacts, mneme/relay/plexus shipped changes, and a closed-loop experimental outcome synthesized from real benchmark artifacts.

## 2026-07-09 update: executable preflight receipts

- REQ-002 Forum routing: `harness.cmd forum-route` produced `C:\tmp\forum_route_receipts_20260709_current.json` and stored route receipt artifacts under `C:\tmp\harness_file_store_current`.
- REQ-004 tool integration: `harness.cmd mcp-health` produced `C:\tmp\mcp_tool_health_20260709_current.json`. Result: 11 roots configured, 0 missing roots, `forum` and `telos` observed healthy, `index` observed degraded with `transport_closed`, 8 configured tools unobserved.
- REQ-004 tool readiness: `harness.cmd readiness tools` produced `C:\tmp\tool_readiness_20260709_current.json`. Result: 10 tools observed by static profile, 0 missing roots, 0 enterprise-ready tools, mean static score `0.459`, verdicts `7` prototype-with-gaps and `3` incomplete-static.
- REQ-009 executable harness: `harness.cmd plan` produced `C:\tmp\harness_closed_loop_seed_plan_20260709_current.json`. Result: 29 planned steps, 0 executed benchmark rows, 0 endpoint probes, 0 provider/model calls.
- Evidence status: metadata preflights executed; tests, endpoint probes, provider calls, model-weight reads, and benchmark workloads were not executed in this step.

## 2026-07-09 update: REQ-006 / REQ-009

- REQ-006 benchmark rigor: agentic task manifests are now ingested as planned-only coverage in coverage and outcome reports, preventing benchmark-credit inflation while preserving planned coverage shape.
- REQ-009 forum accountability ledger: added `forum_ledger_deep_verify_scaling` benchmark contract for `verify(deep=True)` scaling, redaction, crash recovery, tamper detection, and checkpoint pressure.
- Evidence status: code and contract written; no tests, validation, or benchmark execution were run in this step.

## 2026-07-09 update: REQ-001 / REQ-006 / REQ-009 / REQ-012

- REQ-001 tool integration: patched Index MCP failure containment and scan I/O resilience in the local Index checkout.
- REQ-006 benchmark rigor: promoted forum deep-verify and embodied realtime multimodal pressure into the benchmark profile rather than leaving them as loose ideas.
- REQ-009 accountable receipts: forum deep-verify artifacts now have profile, coverage, and outcome signal paths.
- REQ-012 local-model research: Boris/ENBSeries feedback is represented as a planned benchmark contract for tiny/realtime robotics-style model behavior and multimodal grounding.
- Evidence status: code and contracts written; no tests, MCP retest, model-card verification, or benchmark execution run in this step.

## 2026-07-09 update: REQ-006 / REQ-012

- REQ-006 benchmark rigor: embodied realtime multimodal benchmark now has a reproducible metadata-only harness command and planned scorecard surface.
- REQ-012 local-model support: robotics-style latency, sensor grounding, code-drawn visual reasoning, simplified multimodal streams, and affective drift probes are now represented as provider-role x latency-budget x probe rows.
- Evidence status: command/reporting code written; tests, model-card verification, rendering checks, endpoint calls, and benchmark execution were not run in this step.

## 2026-07-09 update: REQ-006 / REQ-007 / REQ-012

- REQ-006 benchmark rigor: embodied realtime is now wired into the default closed-loop seed and benchmark execution matrix rather than living only as a standalone command.
- REQ-007 metric coverage: the execution matrix now records planned evidence gates for `planned_probe_rows`, `dry_scorecard_rows_not_executed`, and `model_leads_unverified`.
- REQ-012 final-output pack: infrastructure, roadmap, capability catalog, and this evidence matrix now record the embodied realtime orchestration boundary.
- Evidence status: code/docs written; tests, seed dry plan execution, model-card verification, rendering checks, endpoint calls, and benchmark execution were not run in this step. Live Index MCP still returned `Transport closed`; live Forum route was available but low-confidence/escalated.

## 2026-07-09 update: REQ-005 / REQ-006 / REQ-007 / REQ-012

- REQ-005 cross-harness comparison: added a non-executing cross-harness manifest generator that creates same-task prompt hashes and planned provider-role receipt rows for Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry/null roles.
- REQ-006 benchmark rigor: cross-harness planned rows are now part of the seed, execution matrix, coverage, and outcome surfaces.
- REQ-007 metric coverage: planned `harness.cross-harness-task-scorecard/v1` rows carry the scorecard metric contract and explicit `not_executed` failure class.
- REQ-012 final-output pack: infrastructure, roadmap, capability catalog, and this matrix now record the cross-harness manifest boundary.
- Evidence status: code/docs written; tests, dry-plan generation, provider calls, endpoint calls, and benchmark execution were not run in this step. Live Index MCP still returned `Transport closed`; live Forum route was available but low-confidence/escalated.

## 2026-07-09 update: REQ-003 / REQ-005 / REQ-006 / REQ-009 / REQ-012

- REQ-003 context/preflight readiness: refreshed the dry-run command deck so current metadata preflights are explicit and reproducible.
- REQ-005 cross-harness comparison: added the cross-harness manifest command to the deck as metadata-only preflight evidence.
- REQ-006 benchmark rigor: added agentic task, cross-harness, and embodied realtime manifest commands to the preflight deck before approval-gated validation/provider runs.
- REQ-009 executable harness: updated the executable manifest expectation so `harness.cmd cross-harness` is part of the front-controller surface.
- REQ-012 final-output pack: command deck record, capability catalog, roadmap, and this matrix now reflect current metadata-only commands.
- Evidence status: files updated; no command deck execution, tests, metadata artifact generation, provider calls, endpoint calls, or benchmark execution were run in this step. Live Index MCP still returned `Transport closed`; live Forum route was available but low-confidence/escalated.

## 2026-07-09 update: REQ-014 / REQ-009 / REQ-012

- REQ-014 schematic maintenance: added a metadata-only schematic drift checker and updated the graph/report to include current cross-harness, embodied realtime, and drift-check surfaces.
- REQ-009 executable harness: added `harness.cmd schematic-drift`, closed-loop seed wiring, and execution-matrix wiring.
- REQ-012 final-output pack: infrastructure, roadmap, capability catalog, schematic report, command deck, and this matrix now record the drift-check boundary.
- Evidence status: code/docs written; no tests, schematic drift command execution, metadata artifact generation, provider calls, endpoint calls, or benchmark execution were run in this step. Live Index MCP still returned `Transport closed`; live Forum route was available but low-confidence/escalated.

## 2026-07-09 update: REQ-005 / REQ-008 / REQ-009 / REQ-014

- REQ-005 cross-harness comparison: added an adapter runtime matrix that exposes manifest readiness and blocking gates for Codex, Flywheel, Claude Code, OpenCode, local 14B, local 32B, and dry roles before provider execution.
- REQ-008 local endpoint support: local 14B/32B readiness now requires endpoint profile metadata with an existing root and agentic workflow support before the profile gate clears; live endpoint gates remain approval-gated.
- REQ-009 executable harness: added `harness.cmd adapter-runtime`, closed-loop seed wiring, execution-matrix wiring, coverage recognition, and outcome signal extraction.
- REQ-014 schematic maintenance: closed-loop schematic graph and schematic drift requirements now include `adapter_runtime_matrix` as a required node feeding the benchmark execution matrix.
- Evidence status: code/docs written; no tests, adapter runtime artifact generation, endpoint probes, provider calls, token-store reads, model-weight reads, or benchmark execution were run in this step. Live Index MCP still returned `Transport closed`; live Forum route was available but low-confidence/escalated.
