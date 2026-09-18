# Compact local models with verified inference

Status: research direction, not a demonstrated frontier comparison or a model
release. Added September 17, 2026. No Bonsai weights have been run for this note.

## Decision and original thesis

Assess whether compression combined with Flywheel's verification, recovery and
reuse can make local systems rival or surpass frontier systems on defined work.
This continues the model-uplift program inside the consolidated Flywheel
repository. The former `local-model` repository is archived. The canonical
method map is [MODEL-UPLIFT.md](../../MODEL-UPLIFT.md); this source assessment
does not establish a result or launch an unbounded training run.

The original thesis in [PROJECT.md](../../PROJECT.md) separates a model that
proposes from a harness that verifies, chains, escalates, caches and witnesses.
[ROADMAP.md](../../ROADMAP.md) makes local verified inference versus frontier
single-shot inference an explicit experimental target. Existing reported
search-and-verification lift is not a frontier comparison; prior continued
pretraining did not establish improved model reasoning under the fixed harness.

The new target includes exceeding, not merely matching, frontier workflow
performance. Astra and Fable 5.1 are requested comparison targets. Exact provider
model IDs, versions, settings and access must be established at execution time;
their availability and performance are not asserted here.

## Release source map

The supplied links resolve to:

- [Bonsai 2 release](https://prismml.com/news/bonsai-2-27b)
- [Whitepaper](https://github.com/PrismML-Eng/Bonsai-demo/blob/main/bonsai-2-27b-whitepaper.pdf)
- [Model collection](https://huggingface.co/collections/prism-ml/bonsai-2)
- [WebGPU kernel demonstration](https://huggingface.co/spaces/webml-community/ternary-bonsai-2-webgpu-kernels)
- [Demonstration repository](https://github.com/PrismML-Eng/Bonsai-demo/)
- [Runtime documentation](https://docs.prismml.com/get-started/introduction)

Release benchmark ratios are vendor results until reproduced. Reduced weight
storage is distinct from reduced parameter count, total inference memory, faster
decoding, and better completed work. A compressed 27B model still has the stated
parameter count; serving also needs runtime buffers, activations and KV cache.

Primary-source assessment found a material boundary in the whitepaper (PDF
page 7): the separately reported long-horizon results are 52.8 versus 69.7 on
Terminal-Bench 2.1 and 60.8 versus 80.6 on SWE-bench Verified, Bonsai versus
Qwen3.8-27B respectively. The 98.2% headline concerns the main 20-benchmark
aggregate, not these long-horizon tasks. These are vendor measurements, without
an independent reproduction here; they motivate a workflow experiment rather
than a parity claim.

The 5.93 GB figure is a language-weight pack, not total serving memory. Public
materials describe ternary group scaling and a Hadamard activation transform
requiring compatible inference code. They do not supply a complete recipe for
re-deriving compressed weights from the higher-precision base. Pinning and
rechecking inference artifacts is distinct from reproducing compression training.

Source versions also matter: the inspected GGUF card presents a 14-benchmark
quality summary while the whitepaper presents 20; their reported runtime figures
also differ. Preserve each source's suite, build and conditions rather than
combining them. The serving docs describe prefix-cache reuse, while the optional
speculative path disables cross-request reuse. Faster single-turn decoding may
therefore lose time in a repeated tool loop. Measure those paths separately.

## Separate hypotheses

| Hypothesis | Proposed test | What a positive result would not establish |
| --- | --- | --- |
| Compression retains useful capability at lower memory cost | Compressed and corresponding higher-precision base under the same harness, task set and decoding budget | Universal retention, reasoning improvement or a hardware-independent speedup |
| Receipts and checked reuse reduce repeated work | Same model with reuse disabled, valid warm reuse, and invalidated/stale reuse controls | Faster intrinsic reasoning or increased model knowledge |
| Search, verification and recovery improve outcomes | Fixed model, controlled candidate/compute budgets, external task checks, stronger baseline and false-success controls | Free quality gain or general model superiority |
| Verified training examples improve the model | Fixed-harness evaluation of weights before/after training, genuinely unseen task families and data-ablation controls | Improvement caused by receipts rather than data selection, extra compute or leakage |
| The local system surpasses a frontier system on defined work | Matched full-workflow comparisons with equivalent tools, context, verification and budgets | Across-the-board superiority over the named model |

Do not combine these hypotheses into one headline. Receipts preserve evidence;
benefits arise from particular mechanisms such as avoided recomputation, useful
selection, better recovery or effective training. Each mechanism needs an ablation.

## Existing mechanisms and missing work

Existing interfaces include `harness/cache.py`, `harness/proof_cache.py`,
`harness/loop.py`, receipt proof/lookup helpers and local endpoint adapters.
Proof-addressed lookup is limited to suitable prompt-independent oracles and
re-witnesses results; a stored pass does not excuse a bad candidate.

`harness/serve.py` implements exact memoization. This is different from true
shared-prefix KV caching, specialized ternary kernels, or reduced generation
cost on novel tasks. No Bonsai integration or validated Bonsai kernel speedup
is established by these existing files. Verify current source revisions before
using them in an experiment.

## Smallest discriminating experiment

Start with a licensed, supported local artifact and one independently checkable
workflow family. Pin model files, tokenizer, runtime, kernels, hardware and the
task/checker versions. First establish runtime correctness and full memory use.

Compare compressed versus higher-precision weights with the same harness.
Separately compare harness features disabled versus verification/search/reuse
enabled. Report cold-cache novel tasks and warm-cache repeated subproblems apart;
include changed requirements that must invalidate prior results. Do not let
cached test answers become apparent reasoning ability.

Include both the original frontier single-shot comparator and a frontier model
using the same effective harness. Otherwise a weak baseline can make system
engineering look like a model breakthrough. Keep tool access and task evidence
equivalent, and show quality versus elapsed time/resource budgets rather than
silently granting one arm more attempts. Fresh cases must stay outside training,
calibration, cache seeding and threshold selection.

Measure verified task completion, false acceptance, abstention/fallback, recovery,
time to correct result, sustained throughput, p50/p95 latency, peak weights plus
KV/runtime memory, and total work including retries and checking. Report energy
only with a measurement method. Keep task-specific results and failures visible;
an aggregate retention ratio can hide a critical weakness.

## Decision and release boundary

The evaluation must inform a concrete choice: adopt a runtime, use a compressed
model for a specified function, collect better data, retain the existing route,
or stop this approach. Declare the criterion and comparison budget before
examining final outcomes. Apply the same evidence standards to Flywheel and
each competing model or organization.

Treat rivalry or superiority as a bounded hypothesis until independent outcomes
support it. A successful scoped comparison can justify that route; broad model
reasoning claims need separate fixed-harness, uncontaminated evidence. Existing
authorization, deterministic acceptance, provenance and release gates remain.
