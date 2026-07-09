# Dry-Run and Preflight Command Deck

Date: 2026-07-09

Status type: command deck, not executed evidence.

Machine-readable deck:

- `C:\dev\local-model\benchmarks\dry-run-preflight-command-deck-v1.json`

## Purpose

This deck turns the current roadmap into exact commands that can generate metadata receipts first, then endpoint/provider benchmark artifacts only after explicit approval.

## Tiers

| Tier | Meaning |
| --- | --- |
| `metadata_only` | May generate local JSON/Markdown artifacts. Must not call model providers, probe endpoints, read model weights, or run benchmarks. |
| `requires_validation_approval` | Requires explicit approval before running tests or validation. |
| `requires_provider_endpoint_approval` | Requires explicit approval before calling providers, local endpoints, Claude Code, OpenCode, Codex Pro, or frontier APIs. |

## Metadata-only preflights

```powershell
.\harness.cmd --print-command plan --out C:/tmp/harness_closed_loop_seed_plan_20260709.json
```

```powershell
python scripts/run_closed_loop_benchmark_seed.py --dry-plan --artifact-dir C:/tmp/harness_closed_loop_seed_20260709 --out C:/tmp/harness_closed_loop_seed_plan_20260709.json
```

```powershell
python scripts/run_endpoint_auth_status.py --out C:/tmp/endpoint_auth_status_20260709.json --markdown-out C:/tmp/endpoint_auth_status_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_benchmark_execution_matrix.py --providers serve,codex,ollama,claude,opencode,dry --run-id benchmark_matrix_20260709 --artifact-dir C:/tmp/harness_benchmark_matrix_20260709 --out C:/tmp/benchmark_execution_matrix_20260709.json --markdown-out C:/tmp/benchmark_execution_matrix_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_schematic_drift_check.py --graph C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json --report C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md --out C:/tmp/schematic_drift_check_20260709.json --markdown-out C:/tmp/schematic_drift_check_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_benchmark_profile_manifest.py --providers serve,codex,ollama,claude,opencode,dry --artifact-roots "C:/tmp;C:/dev/local-model/artifacts" --out C:/tmp/benchmark_profile_manifest_20260709.json --markdown-out C:/tmp/benchmark_profile_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_context_inventory.py --out C:/tmp/context_inventory_20260709.json --markdown-out C:/tmp/context_inventory_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_tool_readiness_receipts.py --tools index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan --base-root C:/dev/public --tool-root aleph=C:/dev/aleph --out C:/tmp/tool_readiness_20260709.json --markdown-out C:/tmp/tool_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_tool_hardening_plan.py --readiness-artifact C:/tmp/tool_readiness_20260709.json --out C:/tmp/tool_hardening_plan_20260709.json --markdown-out C:/tmp/tool_hardening_plan_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_model_endpoint_profiles.py --models 14B,32B --base-root E:/local-model-run --out C:/tmp/model_endpoint_profiles_20260709.json --markdown-out C:/tmp/model_endpoint_profiles_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_adapter_runtime_matrix.py --contract C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json --endpoint-profiles C:/tmp/model_endpoint_profiles_20260709.json --endpoint-auth-status C:/tmp/endpoint_auth_status_20260709.json --out C:/tmp/adapter_runtime_matrix_20260709.json --markdown-out C:/tmp/adapter_runtime_matrix_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_gather_readiness.py --gather-root C:/dev/public/gather --config-roots C:/dev/local-model/configs --config-pattern "gather-*.json" --credential-vars GATHER_DISCORD_BOT_TOKEN,DISCORD_TOKEN --out C:/tmp/gather_readiness_20260709.json --markdown-out C:/tmp/gather_readiness_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_index_receipt.py --lane context-envelope --root C:/dev --index-root C:/dev/public/index --budget 12000 --focus "local-model harness benchmark task set endpoint tools" --hops 2 --mcp-tool index_context_envelope --mcp-status transport_closed --mcp-error-code transport_closed --mcp-error-summary "Transport closed" --artifact-out C:/tmp/index_context_envelope_fallback_20260709.json --out C:/tmp/index_context_envelope_fallback_receipt_20260709.json --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_agentic_task_set_manifest.py --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --adapter C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json --out C:/tmp/agentic_task_manifest_20260709.json --markdown-out C:/tmp/agentic_task_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_cross_harness_manifest.py --task-set C:/dev/local-model/benchmarks/agentic-task-set-v1.json --contract C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json --provider-roles codex_harness,flywheel_harness,claude_code,opencode,local_14b,local_32b,dry --out C:/tmp/cross_harness_manifest_20260709.json --markdown-out C:/tmp/cross_harness_manifest_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_embodied_realtime_multimodal_plan.py --contract C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json --providers dry --latency-budgets-ms 250,500,1000 --out C:/tmp/embodied_realtime_multimodal_plan_20260709.json --markdown-out C:/tmp/embodied_realtime_multimodal_plan_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_model_card_claim_table.py --contract C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json --out C:/tmp/model_card_claim_table_20260709.json --markdown-out C:/tmp/model_card_claim_table_20260709.md --store-root C:/tmp/harness_file_store
```

## Future validation commands

These commands are not authorized by this deck. They are listed so the next execution step is explicit.

```powershell
pytest tests/test_forum_route_receipts.py tests/test_mcp_tool_health_receipts.py tests/test_agentic_task_set_manifest.py tests/test_cross_harness_manifest.py tests/test_adapter_runtime_matrix.py tests/test_embodied_realtime_multimodal_plan.py tests/test_model_card_claim_table.py tests/test_schematic_drift_check.py tests/test_harness_cli.py tests/test_closed_loop_benchmark_seed.py tests/test_benchmark_execution_matrix.py tests/test_benchmark_profile_coverage.py tests/test_closed_loop_outcome_report.py
```

## Future endpoint/provider commands

These commands require explicit provider/endpoint approval.

```powershell
python scripts/run_model_endpoint_gate.py --profile-artifact C:/tmp/model_endpoint_profiles_20260709.json --models 14B,32B --out C:/tmp/model_endpoint_gate_20260709.json --markdown-out C:/tmp/model_endpoint_gate_20260709.md --store-root C:/tmp/harness_file_store
```

```powershell
python scripts/run_closed_loop_benchmark_seed.py --store-root C:/tmp/harness_file_store --artifact-dir C:/tmp/harness_closed_loop_seed_20260709 --out C:/tmp/harness_closed_loop_seed_20260709.json --unisonai-repair-json
```

```powershell
python scripts/run_closed_loop_outcome_report.py --input C:/tmp/harness_closed_loop_seed_20260709.json --out C:/tmp/harness_closed_loop_outcome_20260709.json --markdown-out C:/tmp/harness_closed_loop_outcome_20260709.md --store-root C:/tmp/harness_file_store
```

## Added metadata preflight: Forum route receipts

```powershell
python scripts/run_forum_route_receipts.py --route "Design the next closed-loop harness slice: convert live forum routing decisions into metadata-only stored receipts so Codex/Flywheel benchmark runs can measure route confidence, escalation state, decided lane, communication contract, and failure modes without making provider calls." --observed-confidence 0.1459 --observed-needs-escalation true --observed-domain operator-platform --observed-intent coordinate --observed-posture operator --observed-proof-lane synthesize --observed-domain-lane frontier-foundry --observed-human-contract "Answer as an operator: name the platform move, the tradeoff, the owner, and the next coordinated action." --out C:/tmp/forum_route_receipts_20260709.json --markdown-out C:/tmp/forum_route_receipts_20260709.md --store-root C:/tmp/harness_file_store
```

## Added metadata preflight: MCP tool health

```powershell
python scripts/run_mcp_tool_health_receipts.py --tools index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model --observation "index=TRANSPORT_CLOSED|transport_closed|index_context_envelope returned Transport closed" --observation "forum=MATCH||forum.route returned project-telos validation frame" --observation "telos=MATCH||telos_room returned 5 of 5 flagship tools ready" --out C:/tmp/mcp_tool_health_20260709.json --markdown-out C:/tmp/mcp_tool_health_20260709.md --store-root C:/tmp/harness_file_store
```

## Added executable print preflights: route and MCP health

```powershell
.\harness.cmd --print-command forum-route --route "Route the active Codex/Flywheel local-model closed-loop harness objective." --out C:/tmp/forum_route_receipts_20260709.json --markdown-out C:/tmp/forum_route_receipts_20260709.md --store-root C:/tmp/harness_file_store
.\harness.cmd --print-command mcp-health --tools index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model --observation "index=TRANSPORT_CLOSED|transport_closed|index_context_envelope returned Transport closed" --out C:/tmp/mcp_tool_health_20260709.json --markdown-out C:/tmp/mcp_tool_health_20260709.md --store-root C:/tmp/harness_file_store
```

## Current risks

- `index.index_context_envelope` currently fails with `Transport closed` in the MCP surface.
- Metadata preflight commands are implemented but not executed by this deck record.
- Metadata preflights are not benchmark results and do not prove model quality.
- Endpoint/provider commands are not authorized by this deck.
