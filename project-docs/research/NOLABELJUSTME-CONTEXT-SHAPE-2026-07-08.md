# Public research-context shape: NoLabelJustMe

Date: 2026-07-08

Scope: public Reddit profile and public posts only.

Privacy boundary: this is idea-context mining. Do not infer private identity, health, location, employment, or non-public attributes. Use only public writing patterns as benchmark-design inspiration.

Machine-readable seed corpus: `C:/dev/local-model/dataset/research_context_shapes_nolabeljustme_2026-07-08.json`

## Useful context for the flywheel

The public writing centers on a few patterns that are directly relevant to benchmark design:

- Scoreboards can reward conformity instead of truth.
- Engagement incentives can convert provocation into value extraction.
- Silence/non-engagement can be a useful response to bait.
- A system can appear internally orderly while hiding contradictions against observed reality.
- Words and fluent conceptual posture are not the same as embodied competence.

## Translation into benchmark lanes

### Anti-scoreboard truthfulness

Create tasks where majority or popularity signals conflict with evidence. The correct behavior is to follow evidence, cite precisely, and resist popularity-proxy optimization.

Metrics:

- `evidence_adherence_rate`
- `popularity_proxy_resistance`
- `citation_precision`
- `unsupported_claim_count`

### Provocation resistance

Create agent tasks with hostile comments, mockery, bait, or irrelevant social pressure injected into the context. The correct behavior is to keep task focus, avoid reactive escalation, and complete the requested artifact.

Metrics:

- `task_focus_retention`
- `bait_response_rate`
- `tone_stability`
- `unnecessary_escalation_count`

### Systemillogic detection

Create audits where a benchmark, config, spec, or tool output is internally contradictory. The correct behavior is to identify the contradiction, label the failure mode, and propose a repair.

Metrics:

- `contradiction_detection_rate`
- `missing_assumption_count`
- `benchmark_flaw_label_accuracy`
- `repair_plan_specificity`

### Embodied competence

Create tasks where fluent explanation is insufficient. The model must produce a runnable artifact, cite evidence, and calibrate claims to what actually happened.

Metrics:

- `artifact_correctness`
- `claim_evidence_alignment`
- `overclaim_rate`
- `self_correction_rate`

## Integration rule

These lanes should not replace coding, tool-use, and local-model benchmarks. They should be added as cross-cutting adversarial conditions across existing tasks:

- normal task
- same task with scoreboard pressure
- same task with provocation pressure
- same task with contradictory spec/tool evidence
- same task requiring artifact evidence before final claims

This makes the flywheel measure whether a harness can preserve truth, agency, and evidence under pressure rather than merely produce plausible output.

## Sources

- Reddit profile: https://www.reddit.com/user/NoLabelJustMe/
- Public post, "The Platform Is a Mirror": https://www.reddit.com/r/LessWrong/comments/1u3852u/the_platform_is_a_mirror_reddit_thinks_its/
