# Preregistration addendum: per-rung control replication, and the per-arm hyperparameter-independence rule

**Addendum to:** `prereg.size-invariant-verification.v1`, frozen sha256
`31055c924d48fe67ebdf29ab8f067840f83ccc6ff1d1f469bc0abb2be0dffa08`.

**Sibling addendum, cited for context only:** the confirmatory-abort addendum,
sha256 `09a19497f90ddedc93d297404334c31b62127fe91d5dc1d72dda44d464d87a76`.
Nothing here depends on it.

**Status:** FROZEN when this file's sha256 is appended to the ledger as a
`control-replication-addendum` event. This document does not edit the frozen
preregistration. It extends the parent's controls, and it is written and frozen
BEFORE any policy optimizer exists in this repository, so no result could have
informed it.

**Register:** the `flavored` profile. Calibrated uncertainty is kept.

---

## 1. What this changes, and what it leaves alone

Four additions. Nothing is removed, no endpoint is relaxed, no arm is retired,
and the accept path is untouched.

1. The two spurious control arms replicate per rung rather than once per ladder.
2. Verified-reward improvement becomes claimable only against the same rung's
   spurious delta.
3. Three capacity predictions are registered as predictions, in advance.
4. One measurement rule governs any two-config comparison.

The parent's primary endpoint, its instance set, its K, its seed list, its nine
rungs and two families, and its stopping rule all stand unchanged.

## 2. The spurious controls replicate on every rung

The random-reward arm and the format-only arm run on EACH rung separately. A
single ladder-wide measurement of either is not accepted as covering the ladder.

The reason is a verified external result: reward signals carrying no task
information can still move a Qwen-family model a long way, and the same signals
largely fail to move other families (section 6, row 1). An effect that depends
on the model family cannot be controlled for once and reused across nine rungs,
eight of which are Qwen-family.

R8 (`olmo2:7b`) therefore carries the whole family-dependence test on its own.
That is a real limitation and section 7 states it as one.

**Scope, stated in advance so a later cut is not a silent one.** Initial
replication covers the 1.5B through 7B rungs. The 0.5B rung and both 32B rungs
replicate only if the compute budget allows. A rung whose control did not run is
reported as UNVERIFIABLE for that control. It is never reported as a null, and
it never inherits a neighbouring rung's control.

## 3. The claim rule

An improvement attributed to verified reward is claimable only over the spurious
arm measured on the SAME rung, and never over an untrained baseline:

> claimable improvement on rung r = (verified-reward result on r) minus
> (best spurious-arm result on r)

If the spurious arm on rung r did not run, no improvement is claimable on rung r.
The comparison against no training at all is still reported, because it is
informative about the pipeline, but it does not license a claim about verified
reward.

## 4. Capacity predictions, registered as predictions

These are registered so that a later match cannot be presented as a discovery
and a later miss cannot be quietly dropped.

| id | prediction | confidence |
|---|---|---|
| C1 | Null at 0.5B on the two hardest difficulty bands: no accepted certificate the untrained rung would not also produce. | low |
| C2 | The 0.5B to 1.5B step is larger than the 1.5B to 3B step. | low |
| C3 | The largest returns fall in the 1.5B to 3B range. | low |

The confidence label is low on all three on purpose. Each generalizes other
people's results, on other task families, at other scales, to a certificate
task this ladder has not yet trained on. They are predictions, not findings, and
section 7 repeats that.

## 5. Hyperparameter independence in any two-config comparison

Any comparison of two training configurations, including LoRA rank, learning
rate schedule, and data mix, MUST tune each configuration's hyperparameters
independently. A comparison run under one shared setting is reported as INVALID
for the purpose of ranking the two configurations. It may still be reported as a
single observation of each configuration under that setting.

The rule comes from a first-party reading of the Kimi K3 technical report, which
states the mechanism plainly: two schedules "exhibit markedly different optimal
hyperparameters", so "comparing the two schedules using a shared set of
hyperparameters may unfairly favor one simply because those hyperparameters are
better aligned with it" (section 6, row 5).

**One scoped exception, recorded because the evidence cuts both ways.** The rule
governs comparisons between CONFIGURATIONS, not transfer across MODELS. JustRL
reports one fixed hyperparameter set transferring across two different 1.5B
models without per-model tuning (section 6, row 4). So a shared setting reused
across rungs is not automatically invalid here, and this addendum does not
require per-rung retuning of a recipe that is otherwise held fixed. What it
forbids is deciding that config A beats config B when only A's neighbourhood was
searched.

## 6. Evidence, with a verification verdict per citation

Every citation was retrieved and checked before this document was written, and
each row records what the check found rather than what the source was expected
to say.

| # | source | what it was cited for | verdict |
|---|---|---|---|
| 1 | arXiv:2506.10947, "Spurious Rewards: Rethinking Training Signals in RLVR" | Random reward lifts Qwen2.5-Math-7B on MATH-500 by 21.4 points, against 29.1 for ground-truth reward, and such gains often fail to appear for Llama3 or OLMo2. | VERIFIED. Title, authors, and both numbers match the retrieved abstract. |
| 2 | arXiv:2511.04902, "You Need Reasoning to Learn Reasoning: The Limitations of Label-Free RL in Weak Base Models" | A weak base model cannot generate a usable self-signal; label-free RL depends on the base model's existing reasoning ability, across 0.5B to 7B. | VERIFIED. Supports C1 and C2 directionally. It does not state a threshold, so C1 and C2 remain predictions rather than restatements. |
| 3 | arXiv:2604.00442 | "0.5B zero accuracy everywhere", as a second weak-base support for C1. | **DROPPED. The identifier resolves to "Execution-Verified Reinforcement Learning for Optimization Modeling", which is about a solver used as a deterministic verifier and states no 0.5B result. The claim was misattributed. C1 now rests on row 2 alone.** |
| 4 | arXiv:2512.16649, "JustRL: Scaling a 1.5B LLM with a Simple RL Recipe" | A simple frozen recipe is adequate; one hyperparameter set transferred across two 1.5B models without retuning. | VERIFIED via multiple independent listings. Reported figures: 54.9% and 64.3% mean accuracy over nine mathematical benchmarks, at roughly half the compute of more elaborate recipes. Used for the section 5 exception. |
| 5 | Kimi K3 technical report, section on the learning-rate schedule | Two schedules have different hyperparameter optima, so a shared-setting comparison can favour one unfairly. | VERIFIED verbatim against the report text held locally. |

Row 3 is kept in the table rather than deleted. A citation that failed its check
is part of the record of how this document was built, and removing it would hide
the correction.

## 7. Does not prove

- **NOT_PROVES_THE_PREDICTIONS.** C1, C2, and C3 are preregistered guesses. A
  later match is weak evidence at best, because three coarse ordinal
  predictions over nine rungs have a high chance of partial agreement.
- **NOT_PROVES_FAMILY_INDEPENDENCE_EITHER_WAY.** Family dependence is tested at
  one non-Qwen family, on one rung. A clean control on R8 constrains the
  Qwen-artifact question and does not settle it.
- **NOT_PROVES_THE_DROPPED_CLAIM_IS_FALSE.** Row 3 lost its citation, not an
  argument. Whether a 0.5B model scores zero on hard certificate instances is
  now unsupported in this document and remains open.
- **NOT_PROVES_A_COMPARISON_IS_SOUND.** Independent tuning removes one way for a
  two-config comparison to mislead. Seed variance, evaluation contamination, and
  an unrepresentative data mix all survive it.
- **NOT_PROVES_TRANSFER_TO_THIS_LADDER.** Every verified row above was measured
  on mathematical reasoning benchmarks by other people. This ladder verifies
  certificates against exact checkers, at different scales, and has run no
  reinforcement learning at all. Verifying a citation establishes that the source
  says what it was cited for, and nothing about whether the effect appears here.
- **NOT_PROVES_ANY_ARM_HAS_RUN.** No control arm, spurious or verified, has been
  executed under this addendum. This document freezes the contract before the
  measurement, which is the only order in which it carries any weight.
