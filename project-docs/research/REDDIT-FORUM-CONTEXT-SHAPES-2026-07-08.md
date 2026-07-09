# Reddit Forum Context Shapes - 2026-07-08

## Objective

Curate the source/context shape of four Reddit forums and convert the useful signal into benchmark and tooling changes for the local-model, flywheel, and Codex harness work.

Primary local artifact:
- `C:\dev\local-model\dataset\forum_context_shapes_2026-07-08.json`

Generator:
- `C:\dev\local-model\scripts\forum_context_shapes.py`

## Sources

| Forum | Observed shape | Useful signal | Harness implication |
|---|---|---|---|
| [r/ArtificialInteligence](https://www.reddit.com/r/ArtificialInteligence/) | High-signal AI curation with explicit flairs and anti-noise norms | Research/build/news/opinion posts are expected to provide mechanism, context, and discussion value | Add source-quality scoring before forum-derived material enters benchmark sets |
| [r/processing](https://www.reddit.com/r/processing/) | Creative-code help forum with reproducible snippets, visual output, and beginner debugging | Code, clear titles, expected behavior, and runtime errors matter more than broad prose | Add grounded code-help cases with missing-context traps and visual-state expectations |
| [r/accelerate](https://www.reddit.com/r/accelerate/) | Accelerationist trend radar and pro-AI narrative stream | Good for adoption pressure, narratives, and weak-signal discovery; weak as direct evidence | Add evidence-tier labels so forum trends do not become benchmark claims |
| [r/ArtificialNtelligence](https://www.reddit.com/r/ArtificialNtelligence/) | Broad AI discussion with practical production-agent reliability questions | The tool-timeout/recovery discussion maps directly to agentic fault-injection measurement | Add controlled tool-failure cases and recovery-specific metrics |

## Synthesis

The four forums are not interchangeable source pools.

`r/ArtificialInteligence` is best treated as a curated AI discussion source. Its value is source-shape discipline: flairs, role labels, high-signal posting norms, and explicit rejection of low-context hype or tool spam. The harness should use this pattern as an ingest filter: preserve mechanism, evidence, artifact, and discussion value; down-rank bare product links and unsupported claims.

`r/processing` is a reproducible-context source. It repeatedly pressures the agent toward grounded debugging: show code, state the visual expectation, cite the error, and do not invent missing snippets. This maps to local-model benchmarks because it creates measurable failure modes: hallucinated unseen code, over-completion of educational tasks, and text-only answers that omit expected visual state.

`r/accelerate` is useful as a narrative/trend source, not as benchmark evidence. The harness should retain adoption and market-context signals while gating factual claims behind primary-source verification. This prevents forum ideology or meme velocity from contaminating measured outcome tables.

`r/ArtificialNtelligence` is broad and noisier, but the agent-recovery thread is directly relevant. It surfaces the benchmark gap in the current harness: clean-path task completion is not enough. The flywheel and Codex comparisons need controlled tool faults and scoring for retry, fallback, typed escalation, receipt completeness, and silent-failure avoidance.

## Benchmark Cases Added To The Dataset

The dataset now defines five benchmark seeds:

- `forum_high_signal_curation_v1`: classify forum sources as benchmark-worthy, trend-only, needs-more-context, or reject.
- `forum_processing_repro_debug_v1`: debug creative-code prompts while respecting missing context and visual expectations.
- `forum_agent_recovery_faults_v1`: inject controlled tool failures and score recovery behavior.
- `forum_trend_evidence_gate_v1`: separate measured evidence, plausible hypotheses, and narrative-only signals.
- `forum_signal_preservation_v1`: preserve source identity, uncertainty, oracle checks, and metrics while transforming context into executable benchmark cases.

## Measurement Changes

The most important new measurement lane is `forum_agent_recovery_faults_v1`.

Required harness metrics:
- `recovery_success_rate`
- `silent_failure_rate`
- `retry_budget_compliance`
- `fallback_quality`
- `receipt_completeness`
- `p95_recovery_latency`

Required fault injections:
- tool timeout
- HTTP 429 or rate-limit equivalent
- malformed JSON response
- stale-cache result
- partial success with missing required field

The grading rule should allow multiple valid recoveries. A retry, alternate tool route, typed escalation, or explicit bounded failure can all be correct depending on the injected condition. Silent success after a failed tool call should fail.

## Tooling Hook

Emit benchmark cases:

```powershell
python C:\dev\local-model\scripts\forum_context_shapes.py --format benchmark-json --output C:\dev\local-model\artifacts\forum_benchmark_cases_2026-07-08.json
```

Render this synthesis from the dataset:

```powershell
python C:\dev\local-model\scripts\forum_context_shapes.py --format markdown --output C:\dev\local-model\project-docs\research\REDDIT-FORUM-CONTEXT-SHAPES-2026-07-08.generated.md
```

Validate the dataset shape:

```powershell
python C:\dev\local-model\scripts\forum_context_shapes.py --format validate
```

## Next Integration Step

Wire the emitted `forum.benchmark-case-set/v1` cases into `scripts/run_flywheel_integration_benchmark.py` as a new task source, then run the same case set against:

- Codex harness with `gpt-5.3-codex-spark`
- Flywheel harness with the same model endpoint
- Local 14B and 32B model endpoints

The comparison should report clean-path score and fault-injected score separately. A model/harness that performs well only without tool faults is not agentically production-ready.
