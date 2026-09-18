# Flywheel model uplift

Status: active research direction, September 17, 2026. Methods and experiments
have different maturity levels; this document makes no general superiority claim.

## Canonical home and objective

Flywheel owns this work. The former `local-model` and other pre-Flywheel projects
are archived and consolidated into this repository. Preserve their ideas and
historical evidence here; do not resume separate development in archived repos.
Model weights, runtime environments and experiment outputs may live outside the
checkout for capacity and privacy. They remain artifacts of the Flywheel program.

The objective is progressively smaller-footprint local systems that can rival
or surpass existing competitors on useful completed work, including the operator's
requested Astra, Fable 5.1 and Mythos 5.1-class comparisons. Smaller footprint can
mean fewer parameters, lower precision, reduced working memory or less computation; report
these separately. Pin actual competitor versions and access when running a test.

There are two distinct deployment targets: compressing accessible, licensed
weights and matching frontier-class outcomes with a different local model plus
the harness. A named comparison target does not establish access to its weights
or permission to reproduce them. Evaluate whichever route is actually available;
do not equate a compact open model with a compressed copy of a proprietary model.

Two forms of uplift matter. **Model uplift** changes capabilities of the weights
under a fixed harness. **System uplift** improves completed work through selection,
retrieval, search, checking, recovery and reuse. Both can be valuable; attribution
requires holding one fixed while changing the other.

## Methods to assess

| Candidate method | Intended benefit | Discriminating test |
| --- | --- | --- |
| Outcome-checked training data and targeted adaptation | Learn useful decisions and repairs in smaller weights | Fixed-harness before/after evaluation on unseen source groups; equal-data and compute controls; preserve negative transfer |
| Candidate-aware classifier heads | Avoid generation for routing, tool relevance, context ranking and escalation proposals | Same encoder/data/tuning budget for pooled, bi-encoder and candidate-conditioned attention heads; changing menus and abstention cases |
| Batched decisions and shared-prefix inference | Amortize repeated state processing | Compare independent versus dependent questions; report prefill, scoring, generation, cache misses and whole-workflow time |
| Compressed weights and compatible kernels | Reduce memory while retaining useful capability | Same base/harness across precisions; actual runtime correctness, full working memory and long-horizon quality |
| Verified search and local recovery | Find correct results despite imperfect proposals | Same model with/without search under explicit attempt and elapsed-time budgets; independently checked end states |
| Receipt-bound reuse and re-derivation | Avoid recomputing valid prior work while preserving checkability | Cold versus warm tasks, changed requirements, invalidated witnesses and wrong-result controls; account for recheck cost |
| Local correctness and performance feedback | Make failures diagnosable and repairs testable | Ablate feedback channels; measure checked improvement, repair overhead and reward/outcome disagreement |
| Context selection with recoverable state | Reduce irrelevant input without losing obligations | Delayed-reference and interrupted-task tests; critical-drop rate, recovery success and total completion time |

These are candidates, not a claim that all are implemented or mutually additive.
Receipts do not accelerate reasoning by themselves. A useful gain must come from
a specific mechanism, such as avoiding redundant computation, selecting a better
candidate or learning from independently checked outcomes. Re-derivable evidence
does not make an incorrect criterion true.

## Current evidence and next decisions

- The original verified-inference thesis is retained in [PROJECT.md](PROJECT.md)
  and the historical [ROADMAP.md](ROADMAP.md). Historical search lift is not a
  frontier comparison or evidence that prior continued pretraining improved the
  base model generally.
- The [classifier specification](project-docs/specs/SPEC-classifier-model.md) and
  [Experiment 001](docs/CLASSIFIER-EXPERIMENT-001.md) record trained prototypes.
  Familiar synthetic examples and inspected challenge cases are development
  diagnostics. They do not authorize production selection or establish general
  workflow improvement. [Experiment 002A](docs/CLASSIFIER-EXPERIMENT-002A.md)
  executed new synthetic state transitions: neither frozen learned model completed
  a form, while rules completed all nine feasible cases. This rejects naive
  integration into that action domain and prioritizes suitable outcome-labeled
  data before controlled architecture ablations and training expansion.
- [Experiment 002B](docs/CLASSIFIER-EXPERIMENT-002B.md) tested relevant workflow
  data at a fixed training budget. Both encoder arms still completed zero of
  21 cases; treatment collapsed to abstention and regressed on an older
  diagnostic. These weights remain advisory research artifacts. The negative
  result narrows the next experiment and does not justify automatic selection.
- The [compressed-model assessment](project-docs/research/BONSAI2-COMPRESSION-FUTURE-HYPOTHESIS-2026-09-17.md)
  preserves the Bonsai 2 lead and its source limitations. It proposes runtime,
  retention and harness comparisons; no Bonsai weights have been run for it.
- Activation monitoring is a separate measurement candidate. Keep environment
  reward, checked outcome, monitor readout and evidence completeness separate.
  A detector signal, or its disappearance after training, is not a checked
  improvement in behavior.

## Competitive standard and release boundary

Use relevant strong competitors under the same task evidence, tool access and
budgets. Give a frontier comparator equivalent harness support as well as retaining
the original single-shot reference. Compare specialists only on supported tasks.
Include deterministic rules where policy is fully specified. Report cost and
latency per correct completion, failures and fallback, resource use, uncertainty,
and the quality/resource tradeoff. Local inference is not resource-free.

Predeclare the useful decision, baseline, acceptance criteria, data split and
change trigger. A result should cause adoption, rejection, further investigation
or justified retention. Recheck any claimed improvement and audit false success.
Holdouts stay outside training, threshold selection and cache seeding; once
inspected for improvements, they become development evidence.

Apply the same relevant criteria to our work and to competitors, customers and
potential partners. Separate vendor reports, inspected source, reproduced results,
and unknowns. A neutral evaluation need not produce equal verdicts. Model behavior
does not by itself establish an organization's practices or causal responsibility.

Learned proposals never authorize actions or replace deterministic acceptance.
Promotion is function-specific and requires demonstrated workflow benefit within
its error budget. Broader training, publication and release retain their existing
provenance, licensing, independent evaluation and release gates. Success on one
workflow does not establish universal superiority.
