# Invention depth: the first measured turn of generation under witness

The loop register proved the invention loop CLOSES (propose, kernel,
store, seed). This note reports how far it turns: can the loop produce
conjectures nobody seeded, at what rate, and at what rung of novelty.

## The mechanism

`harness/conjecture_forge.py`: a deterministic enumeration over a linear
Nat-arithmetic grammar (31 expressions; +, * by constants, truncated -,
min, max) proposes universally quantified equations. The Lean kernel
(4.32.0) is the sole judge via `by omega`, which is a decision procedure
for this grammar, so refusal is evidence against the statement, not a
tactic gap. Novelty is corpus-relative by normalized-statement hash
(alpha- and name-invariant). The novelty ladder grades every survivor:
L0 proved but already held, L1 proved and corpus-absent via the cheap
tactic, L2 corpus-absent where the cheap tactic failed and a strong
proof passed. Reachable by curl: `POST /api/invent {"k": 12}`.

## The measurement (2026-07-14, live kernel)

Full-grammar sweep, artifact
`artifacts/invention/conjecture_sweep_20260714-101110.json`:

| Quantity | Value |
|---|---|
| proposed | 465 (every pair, each judged exactly once) |
| kernel-accepted | 33 (7.1%) |
| refused | 432 |
| declared (kernel unavailable) | 0 |

Survivors chained into the verifiable store under kind `theorem`, each
carrying the statement, its normalized hash, the tactic, and the
kernel's toolchain string. Among them: `n + m = min n m + max n m`
(both orders), `(n + m) * 2 = n * 2 + m * 2`, `n + m - m = n`, full
commutativity instances, and cross-family compositions such as
`m + n - n = max m m` that no one wrote down anywhere in this
repository before the kernel accepted them.

## The honest boundary

- Novelty here means absent from the corpus. The grammar's vocabulary is
  human-chosen; the specific true equations were not. The receipt says
  exactly this and nothing grander.
- Every survivor sits on rung L1: closable by the cheap tactic. This is
  structural, not accidental. The forge's acceptance path IS the cheap
  tactic, so it cannot mint L2 survivors by construction. Depth beyond
  L1 requires a proposer that outruns omega and a stronger proof source.
- 7.1% survival is a property of this grammar's truth density, not a
  model capability claim. No model proposed anything in this run.

## The next increment, named

The 14B (or any roster model) becomes the proposer: sample candidate
statements against the corpus, keep the kernel as sole judge, grade on
the ladder, and measure the model's L1+ yield per hundred proposals
against the enumerator's 7.1% floor. A model that cannot beat blind
enumeration on its own home grammar has measurably no mathematical
taste; one that proposes an L2 survivor has produced something the
cheap decision procedure could not certify. Either outcome is a
finding, and the fork should be sealed before the run.
