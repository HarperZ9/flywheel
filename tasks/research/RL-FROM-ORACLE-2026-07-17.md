# RL from the oracle: a verified-reward training loop

2026-07-17. The build toward a small local model that beats larger ones on the
axes a local model can actually win, using the latest research and our own unfair
advantage. Grounded, not aspirational: what ships here is the loop and its
falsifier; the weight update is the next step.

## The honest target

A locally trainable 9B-14B does not out-*capability* a 2.8T frontier model (Kimi
K3) on raw general reasoning. That is a ~100x compute gap training does not close,
and claiming otherwise is the exact overclaim our measurement discipline exists to
prevent. The winnable, defensible "better than them all" is on the axes a local
model owns: **verified tasks, a target domain, efficiency per correct answer,
cost, locality, privacy, and re-checkable receipts.** Frontier models cannot match
verified-and-local. The mechanism that gets us there is the harness, and the
highest-leverage training move inside it is RL from our own verifier.

## What the current research says, and how it maps

- **Ring-Zero** (arXiv 2607.12395, 1T zero-label RL): RL with no human
  annotations, reward from a verifier; emergent self-verification; two phases
  (discovery then sharpening). The scarce half is a trustworthy verifier. **We
  already own it** (the oracle). Ring-Zero validates the direction at 1T scale.
- **GRPO** (group-relative policy optimization): sample a group of G candidates,
  reward each, advantage = how far each reward sits from the group mean, no value
  model. It fits a small-RAM box (no critic), and the group **is** our best-of-N
  pool. Inference selection and RL training become the same generation step.
- **Schema** (~99% self-reported ARC-AGI-3 public): the 0.51% -> ~99% delta is
  THE HARNESS, and the harness is efficiency-shaped (RHAE rewards fewer actions).
  External validation that the loop, not the model, carries the win.
- **Qwythos** (`empero-ai/Qwythos-9B-Claude-Mythos-5-1M`, Qwen3.5-9B, full SFT
  distilled from Claude Mythos 5, 1M context, ~2M GGUF pulls): the popular route
  is **imitation** distillation, copy the teacher's outputs. Its correctness is
  unverified: an SFT-distilled answer is only as right as the teacher was, and no
  receipt says which. This is precisely the gap RL-from-oracle fills, and Qwythos
  is also a candidate base (9B + 1M context + tool-use for free, then earn verified
  capability on top).
- **Kimi K3** (2.8T open): a plug-in escalation tier for the model-agnostic
  router, and a possible distillation teacher, not a training competitor.

## What shipped (harness/rl_from_oracle.py, tests green)

The GRPO-from-oracle **signal loop**, pure and GPU-free, tested with stubs
(`tests/test_rl_from_oracle.py`, 10 falsifiers):

- `grpo_advantages(rewards)`: group-relative advantages, **zero when the group has
  no spread** (all pass or all fail teaches nothing, and we say so rather than
  inventing a gradient), correctly signed and zero-sum when mixed.
- `RLFromOracle.collect/run`: reuse the proposer, the oracle, and the index-stable
  (temperature, seed) grid the inference loop already uses, so a training group
  has the same diversity guarantee as a best-of-N pool. Reward = `oracle.verify ->
  passed` (1/0). Advantages over the group. A witnessed receipt per group and per
  run.
- `PolicyOptimizer` protocol: the weight update (logprobs + GRPO gradient + KL to a
  reference) sits behind an interface, so the core runs and tests with zero GPU.

Two properties make this ours, not a generic RL loop:

1. **The reward is a re-derivable receipt.** Anyone re-runs the oracle on a
   candidate and reproduces its reward; the training SIGNAL is content-addressed
   (`signal_hash`, `receipt_hash`) and auditable. Ring-Zero's reward and Qwythos's
   distillation data are black boxes; ours is not. A signal-only run IS gradable
   RL-data export (the forum bridge).
2. **The held-out oracle catches reward hacking.** `Task.held_out_cmd` is a check
   the model never sees. A candidate that passes the visible oracle but fails the
   held-out one is flagged `reward_hacked` and withheld from the update, so the
   loop never teaches the gaming. This is the "verifier must be able to fail"
   discipline applied to RL itself.

## What is next (in order)

1. **PolicyOptimizer (QLoRA GRPO).** Implement `update(groups)` over the existing
   phase-2 QLoRA infra: recompute candidate logprobs under the policy, GRPO loss
   with a KL term to the frozen reference, optimizer step on a LoRA adapter. No new
   training framework; the CPT pipeline already loads peft + transformers.
2. **Small-model first run (feasibility, honest).** Prove the loop end to end on a
   1.5B-3B Qwen-Coder before the 14B: generation rollouts are the bottleneck on a
   32GB box, so measure tokens/sec and cost per learnable group first. Report the
   real numbers; no projected wins.
3. **Base choice.** Qwen2.5-Coder-14B (our trained line) vs Qwen3.5-9B / Qwythos
   (newer base, 1M context, distilled reasoning already in). RL-from-oracle on a
   distilled 1M base = imitation for breadth + verification for correctness, the
   two routes composed.
4. **Measure against base, honestly.** Same harness, same task set, report the
   delta with its interval; an interval that includes zero is no uplift, not a
   win. The RL claim earns its way the same way the CPT claim did.

## Why this is the differentiated bet

Everyone can SFT-distill a teacher (Qwythos). Almost no one can do zero-label RL
with a **re-checkable, held-out-guarded** reward, because almost no one built the
verifier. That is the flywheel's occupied niche turned into a training method: not
a bigger model, a better-earned one, with the receipt to prove it.
