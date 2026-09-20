# Classifier model experiments

Flywheel's classifier program targets repeated bounded decisions: choosing a
route, ranking tools, identifying relevant context, and deciding when additional
review is useful. The current code is experimental. No measured production
speedup, general-purpose accuracy, or automatic-selection readiness is claimed.

## Design

The existing `flywheel.decision-request/v1` carries state, candidate descriptions,
eligible candidate IDs, and evidence references. Learned scorers consume those
inputs. Deterministic contracts continue to control eligibility and validate
proposals; model confidence never creates permission to execute a tool.

The comparison includes:

| Method | Purpose | Limitation |
| --- | --- | --- |
| Trainable hashed-feature CPU ranker | Measure a very small local scoring cost | Lexical features; abstention examples currently excluded from weight updates |
| Shared pretrained encoder and family heads | Learn semantic candidate matching while reusing text computation | Training and runtime need optional PyTorch/Transformers dependencies |
| Batched first-token logits | Compare against classification without full answer generation | Raw softmax scores need calibration; shared-prefix KV reuse is not yet implemented |
| Structured generation | Establish an equal-decision-contract generation comparison | Output validity and semantic accuracy must be reported separately |

The initial semantic backbone is ModernBERT-base, pinned to revision
`8949b909ec900327062f0ebf497f51aef5e6f0c8`. Its authors describe a 149M-parameter
English/code encoder with an Apache 2.0 license. Those upstream properties do
not establish the quality of the Flywheel fine-tune. See the
[upstream model card](https://huggingface.co/answerdotai/ModernBERT-base).

Training code belongs under `train/`. It is optional and is never imported by
the dependency-free verifier. Checkpoints use safetensors plus hashed metadata;
the CPU baseline uses bounded strict JSON. Neither loads executable model code.

## What the Jev discussions contribute

[TypeSafe's Jev description](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
and [confidence documentation](https://docs.typesafe.ai/confidence) motivate
typed decisions, batching independent questions, and exposing uncertainty.
Their public descriptions do not provide enough of the RLCD training recipe to
claim a reproduction. This program implements and measures its own model.

Other shared ideas become experiments rather than assumed results:

- Compare cached/batched classification with generation; do not benchmark only
  against an unnecessarily slow JSON prompt.
- Test small specialized models on their intended tasks before making broad
  model comparisons.
- Use local correctness checks and workflow outcomes as feedback, while keeping
  teacher judgments distinguishable from independently checked labels.
- Rank optional context by its effect on later work. Token reduction alone is
  insufficient; retain authority, evidence, dependency, and recovery information.
- Investigate adapter initialization and distillation only after a reproducible
  baseline exists. Combining techniques is not itself evidence of improvement.

## Data and evaluation

Every example records family, source group, the decision request, acceptable
choices or explicit abstention, and label provenance. Dataset validation is not
label validation. The initial generated corpus is a diagnostic dataset, not an
independent benchmark of real agent work. Its partitions reuse 23 semantic
scenarios with different sentence forms. They are a paraphrase diagnostic, not
a source-independent holdout. A later 24-case challenge was authored after the
first weights were frozen; its labels are still synthetic reviewer judgments.

The split manifest keeps source/template groups separate. Input identity removes
example IDs, candidate IDs/order, labels, and provenance before duplicate checks.
It normalizes whitespace and case. This detects exact normalized duplication,
not every semantic paraphrase or pretraining overlap.

Training, temperature fitting, threshold selection, and final evaluation need
separate data. Temperature fitting reports the loss change without claiming
unseen calibration. Threshold screening uses a fixed grid and simultaneous
one-sided binomial bounds. Those bounds require representative independent
cases; generated paraphrases do not satisfy that assumption merely by having
different text.

Report per-family quality, abstention coverage, wrong-decision cost, required-tool
recall, context-loss failures, and delayed task completion. Report cold/warm
latency, batch size, cache behavior, resource use, and full workflow time.
Missing energy/cost measurements remain null. Schema-valid wrong answers and
always-abstain controls remain in the evaluation.

## Current release boundary

Source implementation, synthetic training, successful checkpoint loading,
integration, and validated production benefit are separate milestones. Promotion
requires outcome evidence for each supported use. The classifier cannot replace
authorization, verification, publication approval, or release gates.

## Local interfaces

The stdlib model is available through `harness.classifier_cli`:

```sh
python -m harness.classifier_cli train --data examples.jsonl --splits splits.json --out cpu-model
python -m harness.classifier_cli score --model cpu-model/model.json --family tool_selection --requests requests.json --out scores.json
```

Optional neural training uses `train.classifier_encoder_cli train`. Supply the
local pretrained checkpoint with `--pretrained-model`, the example JSONL with
`--examples`, and the full validated split manifest with `--split-manifest`.
This full manifest differs from the group-to-split map accepted by the CPU CLI.
The artifact contains trained weights, encoder config, tokenizer files, hashes,
and the training report. The `score` subcommand reloads that artifact locally.

`harness.classifier_workflows.score_workflow_batch(packets, scorer)` is the
shared Python adapter. Packets contain `task_family` and a decision `request`.
Use `BaselineScorer(model)` or `EncoderClassifierRuntime(...)` as the scorer.
The adapter groups independent decisions, verifies request bindings, sanitizes
score envelopes, and returns shadow scores with an abstention proposal and
`fallback_required: true`. Scoring does not modify the caller's workflow.

The first trained checkpoint and its comparison are documented in
[experiment 001](CLASSIFIER-EXPERIMENT-001.md).
The closed-loop [002A](CLASSIFIER-EXPERIMENT-002A.md) and fixed-budget
[002B](CLASSIFIER-EXPERIMENT-002B.md) results hold automatic action selection:
the current weights did not complete the evaluated forms.
