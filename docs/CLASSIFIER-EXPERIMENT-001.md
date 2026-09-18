# Classifier experiment 001

Status: implemented and trained locally; automatic selection held.

## Question

Can a shared pretrained encoder with learned decision heads improve on a small
CPU ranker across routing, tool selection, context relevance, and escalation?

## Method

The CPU comparator used 2,048 hashed features and 60 training epochs. The neural
model used the pinned ModernBERT-base backbone, four candidate-scoring heads and
four abstention heads. Candidate scores use the state embedding, description
embedding, their product, and absolute difference. Candidate IDs are not features.

The neural run trained the last two encoder layers and the heads for eight
epochs, with seed 1729, encoder learning rate 0.00002, head learning rate 0.001,
gradient accumulation of four examples, and a 256-token input limit. It performed
138 optimizer steps over 552 example presentations. Training used the local
RTX 4090, PyTorch 2.6.0+cu124 and Transformers 5.12.1. The resulting safetensors
checkpoint was reloaded before evaluation.

Both models trained on 69 examples. The initial corpus contains 23 original
synthetic scenarios, rephrased into 69 training, 46 calibration, and 46 test
examples. These partitions share scenarios. A perfect score here measures fitting
those scenarios across sentence forms, not independent workflow generalization.

After freezing the weights, 24 additional challenge cases were authored, six per
family. They include negation, quoted instructions, missing preferences, stale
records, interrupted work, and ownership conflicts. Labels are synthetic
reviewer judgments. No human-independent adjudication or real downstream agent
outcome was measured. No retraining used these challenge cases.

## Observations

| Partition | CPU ranker | Neural classifier |
| --- | ---: | ---: |
| Familiar-scenario rephrasings | 37/46 | 46/46 |
| Additional challenge scenarios | 8/24 | 15/24 |

| Challenge family | CPU ranker | Neural classifier |
| --- | ---: | ---: |
| Routing | 2/6 | 5/6 |
| Tool selection | 2/6 | 5/6 |
| Context relevance | 1/6 | 3/6 |
| Escalation | 3/6 | 2/6 |

One tool-selection challenge asked to find a function and explicitly said not to
run tests. The neural classifier selected the test-running candidate with about
0.936 raw probability. The contract accepted its shape and candidate membership;
that did not make the choice correct. Deterministic eligibility and authorization
remain separate requirements.

Temperature fitting on the familiar synthetic calibration partition chose 0.125
for every family. Applying those fits to the challenge increased log loss in
every family. For example, tool-selection log loss rose from about 1.046 to
5.767. The data mismatch made scores more confident without making them more
correct. These fits are retained as a negative result and are not enabled.

The challenge inference used one six-request batch per family. CPU batch time
amortized to roughly 0.73–1.08 ms per request. Neural inference with an empty
embedding cache amortized to roughly 4.66–4.91 ms after the first batch; the first
batch was about 66.68 ms per request including startup effects. These are a few
batch observations, not robust latency percentiles, single-request latency, or
full workflow speedups. The CPU comparator remains cheaper on these measurements.

The saved neural checkpoint also scored all four families through the shared
workflow adapter. Every result remained a shadow score with an abstention
proposal and the existing fallback required. No external action was executed.

The local Qwen2.5-Coder-14B-Instruct comparator subsequently ran on the same 24
challenge requests, using NF4 quantization, bfloat16 compute and batches of four.
First-token scoring matched 20/24 labels (routing 5/6, tool selection 6/6,
context relevance 4/6, escalation 5/6). This path does not implement shared-prefix
KV reuse. It is a stronger observed quality comparator than the trained encoder.

Unconstrained JSON generation returned Markdown-fenced JSON on all 24 requests,
despite an instruction to return bare JSON. The strict contract accepted none.
A separately recorded post-hoc diagnostic removed only an exact outer JSON
fence, revealing 17/24 correct choices. This diagnostic is not the original
contract score or a grammar-constrained baseline. Preserve both results; the
zero must not be presented as zero semantic decision accuracy.

The six batches totaled about 3.661 seconds for first-token scoring and 22.735
seconds for JSON generation, excluding model load. These correspond to 152.5
and 947.3 ms per request when amortized over the batch workload. Different prompt
contracts, startup effects and a shared desktop GPU limit the comparison. This
does not establish a Jev-relative win or full-workflow acceleration.

## Decision

The neural architecture is a viable experimental implementation, but this
checkpoint is not ready for automatic routing, context deletion, or escalation
decisions. Its improvement over the CPU comparator is uneven and the corpus is
too small and repetitive for broad claims.

The next data work must collect varied workflow outcomes, contrastive negation
cases, unsupported choices, delayed context dependencies and explicit permission
state. Split by original scenario/session before paraphrasing. Treat the current
challenge as development evidence after this inspection; create a fresh sealed
evaluation before further quality claims.

Add exact-prefix reuse and grammar-constrained generation to the measured
first-token and unconstrained-generation baselines, and compare the existing
router. Evaluate downstream task
success, required-tool recall, critical context retention and error cost. Retain
the small CPU baseline for workloads where its lower cost is useful.

## Artifact identities

- CPU model: `classifier-baseline:6dea945fe0ec3cb9`.
- Neural model: `classifier-encoder:509daed51f880563`.
- Neural weights SHA-256:
  `509daed51f880563b8b16c7f21979a4e53a2b170695281fab61a39f0c987cc67`.
- Challenge split manifest SHA-256:
  `b74efd5ec03cc5c964e540886ff893b6bfa3adfc1c604c0daeb78a7293edb26b`.

Artifacts and raw predictions remain local. This report does not imply a release,
deployment, adoption, independent benchmark win, or validated production benefit.
