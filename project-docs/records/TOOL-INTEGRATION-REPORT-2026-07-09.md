# Tool Integration Report

Date: 2026-07-09

Scope: Codex/Flywheel local-model harness integration across the local tool corpus.

Status type: current integration evidence, not a completed validation result.

## Evidence snapshot

Observed local roots:

- `C:\dev\aleph`
- `C:\dev\local-model`
- `C:\dev\public\crucible`
- `C:\dev\public\forum`
- `C:\dev\public\gather`
- `C:\dev\public\index`
- `C:\dev\public\mneme`
- `C:\dev\public\plexus`
- `C:\dev\public\relay`
- `C:\dev\public\telos`
- `C:\dev\public\pubscan`
- `C:\dev\tools`

Observed harness integration scripts:

- `C:\dev\local-model\scripts\run_context_inventory.py`
- `C:\dev\local-model\scripts\run_tool_readiness_receipts.py`
- `C:\dev\local-model\scripts\run_tool_hardening_plan.py`
- `C:\dev\local-model\scripts\run_gather_readiness.py`
- `C:\dev\local-model\scripts\run_index_receipt.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_manifest.py`
- `C:\dev\local-model\scripts\run_benchmark_profile_coverage.py`
- `C:\dev\local-model\scripts\run_benchmark_execution_matrix.py`
- `C:\dev\local-model\scripts\run_harness_comparison_report.py`
- `C:\dev\local-model\scripts\run_closed_loop_benchmark_seed.py`
- `C:\dev\local-model\scripts\run_closed_loop_outcome_report.py`

Observed MCP/tool state in this session:

- `forum.route` is callable. It routed narrower evidence/status work to project-telos, and escalated the broader integration-report request across multiple lanes.
- `index.index_context_envelope` is callable but currently fails with `Transport closed`.
- The Index fallback command path exists through `C:\dev\local-model\scripts\run_index_receipt.py`.
- The Index fallback receipt now carries an explicit `mcp_observation` block so MCP status and error class can be measured alongside CLI fallback output instead of living only in prose.
- The Forum route receipt command exists through `C:\dev\local-model\scripts\run_forum_route_receipts.py`; it stores route prompt hashes and optional route-frame metadata without calling Forum, providers, endpoints, or token stores.
- The MCP tool health receipt command exists through `C:\dev\local-model\scripts\run_mcp_tool_health_receipts.py`; it stores configured root posture and injected non-secret live observations for index, forum, telos, gather, crucible, aleph, mneme, relay, plexus, and local-model.

## Tool integration matrix

| Tool or surface | Local root observed | Codex/MCP status | Harness integration status | Next gate |
| --- | --- | --- | --- | --- |
| `index` | Yes: `C:\dev\public\index` | MCP context envelope currently fails with `Transport closed`. | Local fallback receipt script exists and now records MCP observation status/error fields alongside CLI fallback output. | Fix or stabilize MCP transport, then compare MCP output against fallback receipt output. |
| `forum` | Yes: `C:\dev\public\forum` | `forum.route` callable. | Route prompt hashes and optional observed route-frame metadata are now stored by the closed-loop seed through `forum_route_receipts`. | Execute the metadata receipt and compare future route confidence/escalation drift across runs. |
| `telos` | Yes: `C:\dev\public\telos` | `telos_room` returned `MATCH` with 5 / 5 flagship tools ready in this slice. | MCP health receipts can store Telos room status alongside index/forum observations. | Execute MCP health receipt and compare Telos room readiness drift across runs. |
| `gather` | Yes: `C:\dev\public\gather` | Not live-tested in this slice. | `run_gather_readiness.py` exists and is wired into closed-loop seed. | Execute gather readiness and add source-specific intake receipts. |
| `crucible` | Yes: `C:\dev\public\crucible` | Not live-tested in this slice. | Local root is observed; direct harness command linkage is not proven in this report. | Add or verify crucible-specific readiness and benchmark intake receipts. |
| `aleph` | Yes: `C:\dev\aleph` | Not live-tested in this slice. | Local root is observed; direct harness command linkage is not proven in this report. | Decide whether aleph belongs in readiness, benchmark, or release lanes, then add receipts. |
| `mneme` | Yes: `C:\dev\public\mneme` | Not live-tested in this slice. | Covered by tool readiness and hardening-plan commands for mneme/relay/plexus. | Execute readiness, implement hardening items, and record shipped changes. |
| `relay` | Yes: `C:\dev\public\relay` | Not live-tested in this slice. | Covered by tool readiness and hardening-plan commands for mneme/relay/plexus. | Execute readiness, implement hardening items, and record shipped changes. |
| `plexus` | Yes: `C:\dev\public\plexus` | Not live-tested in this slice. | Covered by tool readiness and hardening-plan commands for mneme/relay/plexus. | Execute readiness, implement hardening items, and record shipped changes. |
| `pubscan` | Yes: `C:\dev\public\pubscan` | Not live-tested in this slice. | Closed-loop docs reference pubscan/resource profiles, but direct execution evidence is not captured here. | Add pubscan profile receipts to the standard seed artifact bundle. |
| `local-model` | Yes: `C:\dev\local-model` | Active working harness. | Provides file store, executable wrapper, benchmark profile/coverage/matrix, comparison, seed, and outcome surfaces. | Run dry plan, focused seed, coverage, comparison, and outcome against one shared run id. |

## Current integration verdict

The local tool corpus is discoverable and partially wired into the Codex/Flywheel harness loop. The strongest current integration is the local-model harness itself plus the reporting/readiness commands around `index`, `forum`, `gather`, `mneme`, `relay`, and `plexus`.

The weakest current integration is live tool execution evidence. Several roots exist, but root presence is not the same as a proven Codex-facing capability. The next maturity jump requires executing the metadata-only preflights and storing their receipts under one run id.

## Immediate integration actions

1. Run closed-loop dry plan and inspect command assembly.
2. Run context inventory, tool readiness, gather readiness, benchmark profile, and benchmark execution matrix preflights.
3. Execute `forum` route-frame receipts through the closed-loop seed so routing decisions become auditable artifacts.
4. Execute MCP tool health receipts so callable/degraded/unobserved/missing-root posture becomes auditable across flagship tools.
5. Stabilize `index` MCP transport or make the fallback wrapper the explicit default until the transport is fixed.
