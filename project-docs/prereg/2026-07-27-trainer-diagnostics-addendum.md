# Preregistration addendum: trainer diagnostics contract

**Addendum to:** `prereg.size-invariant-verification.v1`, frozen sha256
`31055c924d48fe67ebdf29ab8f067840f83ccc6ff1d1f469bc0abb2be0dffa08`.

**Status:** FROZEN when this file's sha256 is appended to the ledger as a
`trainer-diagnostics-addendum` event. This document does not edit the frozen
preregistration; it cites it and adds a contract, using the same
hash-committed-before-the-run mechanism the parent derives its force from.

**Register:** the `research` profile. Calibrated uncertainty is kept; the claim
reads no stronger than its evidence.

---

## 1. Why this exists, before the trainer does

The parent preregistration keeps `PolicyOptimizer` an unimplemented Protocol
(parent section 9). This addendum freezes what every future training run under
verified reward MUST log, committed now so a trainer cannot later choose the
diagnostics that flatter its result.

The specific reason is a convergent 2026 finding: a verified-reward gain and a
spurious-reward gain look identical on the metric a trainer usually reports.

- "Spurious Rewards Paradox" (arXiv:2601.11061, ICML 2026): RLVR can lift a
  score by activating a memorization shortcut, an Anchor-Adapter circuit, rather
  than by improving reasoning.
- "Exploration vs Exploitation: Rethinking RLVR through Clipping, Entropy, and
  Spurious Reward" (arXiv:2512.16912, ICLR 2026): both a spurious reward and
  entropy minimization raise reasoning scores through the same mechanism,
  clipping bias that reduces policy entropy toward more deterministic outputs.
- "SAGE: Shaping Anchors for Guided Exploration in RLVR of LLMs"
  (arXiv:2605.18864): RLVR improves pass@1 while failing to improve pass@k,
  which is the signature of an elicitation gain rather than a capability gain.

The parent already froze the two controls that make this detectable: a
random-reward arm and a format-only-reward arm (parent section 4). This addendum
freezes the diagnostics that let those controls do their work. Without policy
entropy per arm, an entropy-collapse gain is invisible; without pass@k across k,
an elicitation gain reads as a capability gain.

## 2. The contract

Any future training run under verified reward, on any rung, MUST emit a
diagnostics record per arm per checkpoint that carries every field below.
Absent values are recorded as null, never omitted, so a missing measurement is
distinguishable from a bug in the reader. A run that cannot emit a field states
why in a `null_reasons` map.

Required fields, per arm per checkpoint:

- `arm`: one of the frozen arm names (single, best_of_k, random_of_k,
  placebo_of_k, pass_at_k, and the two reward controls random_reward,
  format_only_reward).
- `rung`: the rung id R1..R9.
- `step`: the training step, integer.
- `policy_entropy`: mean token-level entropy of the policy over the eval batch,
  in nats. This is the field the entropy-collapse literature turns on.
- `answer_perplexity`: perplexity on the answer tokens of the eval batch.
- `pass_at_k`: a map from k to the pass@k estimate, for every k the run scores.
- `reward_mean` and `reward_std`: the reward signal's own distribution, so a
  degenerate reward (all-equal, the placebo failure mode) is visible.
- `kl_to_ref`: KL from the reference policy, since the reverse-KL anchor is the
  exploration limiter SAGE names.
- `grad_norm`: the update magnitude, null if not available.
- `n_eval`: the eval-batch size behind every number above, the denominator.

## 3. The predictions, frozen now

These are predictions, not results. They are frozen so that a later run cannot
present a confound as a success.

- On the random-reward and format-only-reward control arms, any pass@1 gain MUST
  be accompanied by a policy-entropy drop. A pass@1 gain on a control arm with
  entropy held roughly constant would falsify the entropy-collapse account for
  this stack and is reportable as such.
- A verified-reward gain that appears at pass@1 but is absent at pass@k is
  recorded as an elicitation gain, not a capability gain, and the claim language
  says so.
- If a control arm reaches the same pass@1 as the verified-reward arm, the
  verified-reward result on that rung is uninterpretable and is published as a
  null, not withheld.

## 4. What this does not prove

- A frozen contract is not a trainer. Emitting these fields does not make a
  training run correct; it makes the run's confounds visible.
- The diagnostics distinguish an entropy-collapse gain from a verified-signal
  gain correlationally, per arm, not mechanistically. They narrow the space of
  honest interpretations; they do not identify the circuit.
- Family dependence is tested at n=1 non-Qwen family, the R8 olmo2 rung. A clean
  olmo2 control does not generalize to families untested here.
- pass@k is truncated by the pool's K. The parent caches K=4 candidates per
  instance with no early stopping, so the local pass@k curve stops far below the
  k at which the literature's crossover appears. The curve reports what K allows
  and says where it stops.

## 5. Freeze record

To be completed at freeze; this document is not frozen until they are.

- [ ] sha256 of this file, computed on the committed bytes (LF)
- [ ] ledger entry appended as a `trainer-diagnostics-addendum` event, citing
      the parent frozen sha256, with its consistency proof from the parent freeze
