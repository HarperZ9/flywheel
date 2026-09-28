# Native classifier model

Status: CPU and encoder prototypes trained and tested locally; architecture
selection, independent workflow acceptance and model release remain open.

## Objective

Train and integrate a reusable local classifier that reduces structured-decision
latency and total workflow cost while preserving task outcomes. Extend the existing
`harness/decision_contract.py` and `harness/decision_evaluation.py` interfaces.
Do not replace their contracts or the deterministic accept path.

## Requirements

- Train a custom candidate-aware model with reproducible weights and provenance.
- Batch independent decisions, reuse shared text computation, return typed
  candidate scores, and abstain when the model cannot support a decision.
- Evaluate routing, tool relevance, context relevance and escalation separately.
- Calibrate on a separate split; raw scores are not calibrated probabilities.
- Preserve candidate eligibility, user authority, evidence references and
  recoverability. Model predictions never authorize execution or certify output.
- Compare equal-contract rules/current-router, lightweight learned model,
  cached batched first-token classification, and structured generation.
- Keep trainer/runtime dependencies isolated from the dependency-free verifier.
- Do not export private session text or use screenshot text as public training
  data without an explicit data-provenance decision.
- Deliver trained model artifacts, reproducible commands, evaluation records,
  supported integrations and runtime acceptance. A schema or wrapper alone is
  not completion.

## First implementation stages

1. Preserve the existing decision request/result v1 contract. Add an optional
   candidate scorer that consumes validated requests and returns a separate
   score envelope plus a proposal accepted by the existing evaluator.
2. Implement a deterministic, trainable CPU linear ranking baseline. It is an
   experimental comparator, not the intended evidence of a powerful universal
   model. Feature extraction must depend on supplied state and candidate
   description, not memorize candidate IDs. Support task-family models and
   bounded batch inference with shared feature caching.
3. Build dataset validation and group-disjoint train/calibration/test manifests.
   Every example records label source and source-group identity. Unknown labels,
   synthetic diagnostic controls and reviewed outcomes remain distinguishable.
4. Select and train a compact encoder/ranker or a compact local decoder with
   decision heads after inspecting existing weights, license and hardware.
   Compare its quality, cost and calibration with stage 2 and first-token logits.
   Distillation labels remain weak labels unless independently checked.
5. Add calibration and task-specific selective-risk evaluation, then shadow
   adapters for the existing router/tool/context workflows. Promote only measured
   useful changes and preserve fallback.

## Baseline contract

Training input is a bounded list of examples containing `task_family`,
`source_group`, a valid `flywheel.decision-request/v1` request, one or more
`acceptable_choice_ids`, and label provenance. Empty acceptable choices represent
explicitly adjudicated abstention, not missing labels. The baseline may initially
train only examples with an acceptable eligible choice and must report excluded
abstention cases rather than mislabel them.

The score envelope records model/artifact identity, request hash, candidate IDs,
scores, scoring latency and calibration status. Scores from the baseline are
uncalibrated. Inference must not auto-promote the largest score into a verified
result or bypass deterministic eligibility. An explicit threshold policy governs
proposals; absent calibration keeps automatic selection disabled.

The model artifact must be bounded JSON with schema/version, feature parameters,
weights, training manifest hash and seed. Reject malformed/nonfinite/oversized
artifacts. No pickle, executable loading or network calls in model loading.
Serialization must reproduce predictions and bind its contents with a checksum.

## Planned ownership

- `harness/classifier_features.py`, `harness/classifier_model.py`, optional
  `harness/classifier_training.py`: baseline feature/model/training implementation.
- `tests/test_classifier_model.py`: meaningful learning, held-out surface-form
  changes, eligibility, batching, serialization and malformed-input controls.
- Dataset/calibration/evaluation adapters and optional encoder training modules:
  next stage after existing-resource inventory. Keep ownership explicit.

## Evaluation and promotion

Split by source session/project/template family, keeping near duplicates and
retries together. Calibration does not train weights; held-out data does not pick
thresholds. Use independently reviewed or reproducible outcome labels for claims.
Existing benchmark examples visible during development are diagnostic data, not
a contamination-free test set.

Report correct/wrong route outcomes, required-tool recall, no-call accuracy,
cost-weighted regret, compaction critical-drop rate and recovery success,
coverage versus selective risk, calibration where justified, p50/p95 cold/warm
latency, total workflow latency, batch/concurrency, cache hits and resources.
Retain null cost/energy fields when not measured.

Compaction preserves pinned instructions, authorization boundaries and referenced
state through deterministic rules. Learn to rank optional spans and validate the
result through delayed-reference and interrupted-task replay. Token savings alone
do not qualify as improvement.

Primary methodological source: TypeSafe's public Jev launch and confidence docs.
Its architecture and RLCD recipe are not publicly specified enough here to
reproduce; this project is not an RLCD reimplementation. Vendor workflow reference
labels and speed ratios are not independent results for this project.

## Completion state

Experiment 001 provides synthetic diagnostic comparisons, not independent
workflow acceptance. Prototype training, artifact loading and shadow adapters
exist. Release and automatic-selection gates remain open.

Experiment 002A adds a closed-loop synthetic form environment and a separately
written outcome checker. Frozen weights did not complete any of the ten cases;
rules completed nine feasible cases and correctly blocked one impossible case.
This rejects naive expansion of those weights into the new action domain.
Relevant-data training has now been tested in Experiment 002B: zero completed
forms in both encoder arms on 21 new synthetic cases. Treatment collapsed to
abstention and lost accuracy on an older diagnostic. Automatic selection and
architecture selection remain open; see `docs/CLASSIFIER-EXPERIMENT-002B.md`.

## Source-informed comparison extension

Compare three heads over the same encoder and frozen source-group split:
pooled state/candidate scoring, bi-encoder similarity, and candidate-conditioned
attention over state tokens. The public Jevlike implementation motivates the
last option; it does not establish TypeSafe's proprietary architecture or a
performance advantage. Hold trainable capacity and tuning budget explicit.

GLiNER-style extraction/classification and Needle-style structured tool models
are specialist comparison candidates. Verify exact model versions, contracts
and licenses before use. Compare each only on functions its actual interface
supports. A browser workflow includes DOM acquisition, candidate construction,
text generation, selection, execution, retries and final-state verification;
router cost alone is not total workflow cost.

Include deterministic rules when the requested policy is fully specified.
Repeated outputs on a toy dilemma do not establish alignment or probability
calibration. Evaluate decisions against scoped user requirements and observable
outcomes, with missing evidence and disputed requirements represented explicitly.

Keep environment reward, independently recomputed outcome, monitor signal and
evidence completeness in separate fields. Activation-monitor integration is
not implemented; absence of a monitor result is not a negative detection.
Existing reward-gap and independent-review interfaces should be reused before
adding a new partner-specific abstraction.
