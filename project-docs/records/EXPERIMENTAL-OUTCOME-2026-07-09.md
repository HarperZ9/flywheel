# Experimental Outcome

Date: 2026-07-09

Status type: preflight outcome, not final experimental results.

## Hypothesis

The Flywheel/Codex harness loop should improve local and frontier model usefulness by combining reproducible task sets, accountable receipts, endpoint gates, tool readiness, benchmark coverage, and outcome synthesis.

## Current outcome

No experimental performance conclusion is supported yet.

Current evidence supports this narrower conclusion:

- the benchmark and outcome infrastructure has been scaffolded;
- required report surfaces now exist as durable records;
- the executable wrapper can now produce metadata receipts and a dry closed-loop benchmark plan;
- the next step is a focused execution seed, not more methodology design.

## 2026-07-09 executable preflight outcome

Preflight commands run through `C:\dev\local-model\harness.cmd` produced current artifacts without endpoint probes, provider/model calls, or benchmark workload execution.

Artifacts:

- `C:\tmp\forum_route_receipts_20260709_current.json`
- `C:\tmp\forum_route_receipts_20260709_current.md`
- `C:\tmp\mcp_tool_health_20260709_current.json`
- `C:\tmp\mcp_tool_health_20260709_current.md`
- `C:\tmp\tool_readiness_20260709_current.json`
- `C:\tmp\tool_readiness_20260709_current.md`
- `C:\tmp\harness_closed_loop_seed_plan_20260709_current.json`
- `C:\tmp\harness_file_store_current`

Observed preflight signals:

- Forum routing receipt recorded one observed route frame: decided lane `project-telos`, domain `model-foundry`, intent `validate`, proof lane `validate`, confidence `0.5`, escalation `false`.
- MCP/tool health receipt covered 11 configured roots. Missing roots: `0`. Healthy observed tools: `forum`, `telos`. Degraded observed tool: `index` with `transport_closed`. Configured but unobserved tools: `8`.
- Expanded tool readiness receipt covered 10 tools: `index`, `forum`, `gather`, `crucible`, `telos`, `aleph`, `mneme`, `relay`, `plexus`, and `pubscan`. Existing tools: `10`. Enterprise-ready tools: `0`. Mean static score: `0.459`. Verdicts: `7` prototype-with-gaps, `3` incomplete-static.
- Dry closed-loop seed plan produced 29 planned steps and no executed results. Planned artifact paths include route, MCP health, executable manifest, registry, benchmark profile, context inventory, expanded tool readiness, endpoint profile/gate, release readiness, gather readiness, pubscan profiles, Index fallback, classifier friction, M7, UnisonAI, coverage, and harness comparison outputs.

Interpretation:

- The harness is now preflight-executable through the Windows front-controller and can record current tool posture as receipts.
- The Index MCP path is still a degraded integration point; the fallback receipt lane remains required until transport stability is repaired.
- Tool roots are discoverable, but enterprise readiness is not established. The strongest current evidence is readiness shape, not shipped enterprise completion.
- No Codex-vs-Flywheel, Claude Code, OpenCode, local 14B, or local 32B performance conclusion is supported by these preflights.

## Missing result evidence

Required before claiming improvement:

- shared task set
- Codex harness run
- Flywheel harness run
- local 14B run where available
- local 32B run where available
- Claude Code/OpenCode run where practical
- benchmark coverage report
- harness comparison report
- endpoint gate artifacts
- closed-loop outcome report

## Preliminary interpretation

The program is measurement-ready but not measurement-complete. The strongest current result is infrastructure readiness; the primary missing evidence is actual run data.

## Next action

Run a focused benchmark seed, then synthesize the outcome from the same run id.
