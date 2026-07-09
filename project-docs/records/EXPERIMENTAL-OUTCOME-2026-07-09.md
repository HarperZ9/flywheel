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

## 2026-07-09 focused execution outcome

Focused run id: `run_20260709T150956_4b913c32efa2`.

Primary artifacts:

- `C:\tmp\harness_closed_loop_seed_focused_postfix_20260709.json`
- `C:\tmp\harness_closed_loop_outcome_focused_postfix_20260709.json`
- `C:\tmp\classifier_friction_postfix_retry_20260709.json`
- `C:\tmp\benchmark_profile_coverage_postfix_retry_20260709.json`
- `C:\tmp\harness_comparison_report_postfix_retry_20260709.json`
- `C:\tmp\model_endpoint_gate_refcheck_20260709.json`
- `C:\tmp\model_endpoint_profiles_32b_integrated_20260709.json`
- `C:\tmp\model_endpoint_gate_32b_integrated_20260709.json`
- `C:\tmp\local_model_launch_readiness_32b_integrated_20260709.json`

What improved:

- Index fallback context now uses bounded root `C:\dev\local-model` and focus `local-model`; the post-fix focused seed recorded `index_context_envelope` as `ok` in `759 ms`.
- Schematic drift was reduced to zero missing required nodes, edges, and files in the fix probe.
- UnisonAI provider-matrix Markdown rendering no longer crashes; the post-fix focused seed recorded the UnisonAI step as `ok`.

Focused seed result:

- Planned steps: `29`.
- Step status: `28` ok, `0` failed, `1` timeout.
- Timeout: `classifier_friction` at the intentionally bounded `240 s` outer step timeout.
- Outcome verdict: `OUTCOME_PARTIAL`.

Classifier retry result for `gpt-5.3-codex-spark`:

| Mode | Quality | Latency ms | Refusal rate | Failure class |
| --- | ---: | ---: | ---: | --- |
| `accountability_first` | `0.775` | `69857` | `0.0` | `low_task_focus` |
| `guardrail_off` | `0.512` | `88214` | `1.0` | `unnecessary_refusal` |
| `guardrail_on` | `0.371` | `166436` | `1.0` | `unnecessary_refusal` |

Observed classifier deltas:

- `accountability_first` vs `guardrail_off`: quality `+0.263`, latency `-18357 ms`, refusal rate `-1.0`, accountability score `+0.5`.
- `guardrail_on` vs `guardrail_off`: quality `-0.141`, latency `+78222 ms`, refusal rate unchanged at `1.0`.

Local endpoint gate:

- `serve` backend reported health and generation ok for the `14B` profile.
- `serve` backend rejected the `32B` profile with `model_ref_mismatch`: expected `Qwen2.5-Coder-32B-Instruct (base, nf4)`, observed `Qwen2.5-Coder-14B-Instruct (base, nf4)`.
- Follow-up 32B-integrated profiles assign `32B` to `http://127.0.0.1:8767`; the live gate now classifies that endpoint as `wrong_service_or_path` with health status `404`, meaning the 32B profile is correct but the live process on that port is not a `harness/serve.py` model endpoint.
- Launch readiness classifies `14B` as `candidate_running_gate_required` on `8765` and `32B` as `port_conflict_wrong_service` on `8767`; observed 32B owner kind is `generic_http_server`.
- `ollama` backend was unavailable for both `14B` and `32B`.
- The corrected endpoint gate blocks any `32B` readiness or publication claim until the serve process/profile mapping is corrected and rerun.

Other benchmark signals:

- M7 source-mined Codex row: quality `0.372`, latency `66509 ms`, pass rate `0.0`.
- M7 governed-agent Codex row: quality `0.436`, latency `54409 ms`, pass rate `0.0`.
- UnisonAI provider matrix: dry fixture passed, Codex row failed with `malformed_action_json`; repair was attempted but did not recover a valid action set.
- Tool hardening plan produced `93` actions: `26` P1 and `67` P2.

Coverage and comparison:

- Benchmark coverage verdict: `COVERAGE_PARTIAL`.
- Benchmark coverage rate: `1.0`.
- Dataset lane coverage rate: `0.5556`.
- Provider coverage rate: `0.6667`.
- Provider-unit coverage rate: `0.0588`.
- Comparison verdict: `COMPARISON_INSUFFICIENT`.
- Reason: no artifact contained both Flywheel and Codex provider-role evidence for the same comparison key.
- Observed provider roles: `codex`, `dry_fixture`, `flywheel`, `ollama_local`.
- Missing provider roles: `claude_code`, `opencode`.

Experimental conclusion:

The first measurable signal supports the receipts/accountability hypothesis only for a narrow Codex classifier-friction slice: in this run, `accountability_first` produced higher quality, lower latency, and fewer refusals than the local guardrail modes for the selected task. This is not yet a full Codex-vs-Flywheel result, because same-key Codex and Flywheel rows are still missing for the executed benchmark comparisons.
