"""pool_arms.py -- every arm as a pure function of one cached pool.

Split from pool.py because the boundary is real: pool.py holds candidates and
knows nothing about selection, this module selects and never generates. Neither
decides correctness; the oracle does.

THE DISTINCTION THIS MODULE EXISTS TO MAINTAIN. In every arm the oracle is the
SCORER. The question an arm answers is whether the oracle also gets to be the
SELECTOR, and whether that earned anything. Conflating those two roles is how
"we verified our way to a better answer" gets claimed for what is really "we drew
more samples".

  single          slot 0 only. The seed-0 temperature-0 draw
  best_of_k       the oracle selects one candidate; `score` grades that one.
                  Self-scored by default, held-out if you pass `score`
  random_of_k     a seeded coin selects one slot, then the oracle scores it.
                  Generation-matched and SELECTION-FREE. This is the control
  placebo_of_k    an acceptor with the oracle's accept rate and zero ground truth
                  selects; the oracle scores. If this matches best_of_k, the
                  oracle's selection earned nothing
  pass_at_k       the curve over budgets 1..k, a diagnostic with no claim on it

WHICH COMPARISONS ARE LEGITIMATE. The rule below is stronger than the one I first
wrote, and I only found that by running the arms instead of reasoning about them.

My first version named the nested pair as `single` against `best_of_k` and
declared `random_of_k` the clean control. The demonstration reported `a_only=0`
for BOTH pairs, which is the nesting signature I had just built this module to
detect. `best_of_k` accepts when ANY slot is accepted, so it is a superset of
every single-pick arm: whatever task random picks and passes, best-of-k passes
too. A hardcoded list of forbidden pairs was the wrong shape of rule.

The general rule, and the reason it is general: **an arm whose SELECTOR is the
same function as the SCORER cannot lose.** If the oracle both chooses the
candidate and decides whether the choice was right, the comparison is circular
and no interval on it is meaningful. That is not a property of which two arms you
name, it is a property of one arm.

So the legitimate comparison needs a HELD-OUT scorer: select with one checker,
score with an independently written one. This repository already has that pair,
`certificates/zarankiewicz.py` and `certificates/independent.py` with their
`cross_check`, which is why `best_of_k` takes an optional `score`. With a held-out
scorer, oracle selection CAN lose, because it can accept something the held-out
checker rejects, and only then is the difference two-sided.

`paired()` enforces this on `scored_by`, not on arm names.

A task with no candidate in any slot is excluded from every denominator and
reported, because grading a task nothing was generated for attributes a harness
gap to the candidate.

THE ACCEPT CONTRACT: `accept(text, task_id) -> bool`, and `score` the same.

The task id is not decoration. Every arm here scores a candidate against the
INSTANCE it was asked about, and an accept function that receives only the text
cannot do that: `CertificateOracle.verify` reads its binding from the task, so
with no task it skips the binding check entirely. Measured on this repository's
own checker, a certificate declaring a 2x2 problem, submitted against the 28x39
instance the candidate was actually given, scores FAIL when bound and PASS when
not. The arms took `accept(text)` at first, which made the unbound version the
only one they could be handed, and every arm's pass rate would have been
inflated by exactly the candidates that answered an easier question than the one
asked. That is the defect `binding_keys` was introduced to close in `verify`,
reappearing one layer up where `verify`'s fix could not reach.
"""
from __future__ import annotations

import math
import random
from math import comb

SCHEMA = "flywheel.pool-arm/v1"
NO_CANDIDATE = "no_candidate"

# An arm scored by its own selector cannot lose, so no two-sided statistic on it
# is meaningful. This is a property of ONE arm, which is why it is not a list of
# forbidden pairs: any pair containing such an arm is circular.
SELF_SCORED = "selector"
HELD_OUT = "held_out"
ORACLE = "oracle"


class ArmError(ValueError):
    """An arm that would report more than the pool holds."""


def _wilson(hits: int, n: int, z: float = 1.959963984540054):
    if n <= 0:
        return 0.0, 0.0
    p = hits / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def _result(name: str, outcomes: dict, oracle_calls: int,
            candidates_used: int, *, selector: str, scored_by: str) -> dict:
    graded = {t: v for t, v in outcomes.items() if v != NO_CANDIDATE}
    hits = sum(1 for v in graded.values() if v is True)
    lo, hi = _wilson(hits, len(graded))
    return {
        "schema": SCHEMA, "arm": name,
        # `selector` chooses the candidate; `scored_by` decides whether the choice
        # was right. Equal is circular, and paired() refuses it.
        "selector": selector, "scored_by": scored_by,
        "outcomes": outcomes,
        "passes": hits, "graded": len(graded),
        "excluded_no_candidate": sorted(t for t, v in outcomes.items()
                                        if v == NO_CANDIDATE),
        "pass_rate": round(hits / len(graded), 6) if graded else 0.0,
        "wilson_95": [round(lo, 6), round(hi, 6)],
        "oracle_calls": oracle_calls,
        "candidates_generated": candidates_used,
    }


def single(pool, accept) -> dict:
    """Slot 0 of every task. The baseline, and the pool's own first draw."""
    outcomes, calls = {}, 0
    for t in pool.task_ids():
        cands = dict(pool.candidates(t))
        if 0 not in cands:
            outcomes[t] = NO_CANDIDATE
            continue
        calls += 1
        outcomes[t] = bool(accept(cands[0], t))
    return _result("single", outcomes, calls, len(pool.task_ids()),
                   selector="none", scored_by=ORACLE)


def best_of_k(pool, accept, *, score=None) -> dict:
    """The oracle selects. `score` decides whether its choice was right.

    With `score=None` the selector IS the scorer, so this arm cannot lose and the
    result is marked `scored_by="selector"`. It is still worth computing: the
    difference against `single` is *verified pass@k*, a real engineering number.
    It is simply not a two-sided comparison, and paired() will say so.

    With an independently written `score` (see certificates/independent.py) the
    arm can lose, because selection can accept what the held-out checker rejects.
    That is the only configuration in which a p-value here means anything.

    Every slot is scored rather than stopping at the first accept, because the
    oracle-call count is part of the cost being compared and short-circuiting
    would understate it.
    """
    grade = score or accept
    outcomes, calls, used = {}, 0, 0
    for t in pool.task_ids():
        cands = pool.candidates(t)
        if not cands:
            outcomes[t] = NO_CANDIDATE
            continue
        used += len(cands)
        chosen = None
        for _, text in cands:
            calls += 1
            if accept(text, t) and chosen is None:
                chosen = text
        # Selection picks one candidate; the scorer grades that one. When the two
        # are the same function this is equivalent to "any slot accepted", and
        # when they differ it is not, which is exactly the point.
        outcomes[t] = bool(grade(chosen, t)) if chosen is not None else False
    return _result("best_of_k", outcomes, calls, used, selector=ORACLE,
                   scored_by=SELF_SCORED if score is None else HELD_OUT)


def random_of_k(pool, accept, *, seed: int) -> dict:
    """A seeded coin selects one slot; the oracle scores that one.

    THE CONTROL. Same generation budget as best_of_k, no verifier guiding the
    choice. If best_of_k does not beat this, verifier-guided selection bought
    nothing that drawing k samples did not already buy.

    The rng is seeded per task from `seed` and the task id, so the arm is
    reproducible and adding a task does not reshuffle the others' draws.
    """
    outcomes, calls, used = {}, 0, 0
    for t in pool.task_ids():
        cands = pool.candidates(t)
        if not cands:
            outcomes[t] = NO_CANDIDATE
            continue
        used += len(cands)
        rng = random.Random(f"{seed}:{t}")
        _, text = rng.choice(cands)
        calls += 1
        outcomes[t] = bool(accept(text, t))
    return _result("random_of_k", outcomes, calls, used, selector="random",
                   scored_by=ORACLE)


def placebo_of_k(pool, accept, *, seed: int, accept_rate: float) -> dict:
    """A selector with the oracle's accept rate and none of its knowledge.

    The spurious-reward control at inference time. It accepts a candidate with
    probability `accept_rate`, ignoring the candidate entirely, and takes the
    first one it accepts. The oracle still scores the result. If this arm's rate
    is statistically indistinguishable from best_of_k, the oracle's selection
    earned nothing, and that is a publishable result rather than a failed run.
    """
    if not 0.0 <= accept_rate <= 1.0:
        raise ArmError(f"accept_rate must be a probability, got {accept_rate}")
    outcomes, calls, used = {}, 0, 0
    for t in pool.task_ids():
        cands = pool.candidates(t)
        if not cands:
            outcomes[t] = NO_CANDIDATE
            continue
        used += len(cands)
        rng = random.Random(f"placebo:{seed}:{t}")
        chosen = cands[-1]                       # fall back to the last slot
        for c in cands:
            if rng.random() < accept_rate:
                chosen = c
                break
        calls += 1
        outcomes[t] = bool(accept(chosen[1], t))
    return _result("placebo_of_k", outcomes, calls, used, selector="placebo",
                   scored_by=ORACLE)


def pass_at_k(pool, accept) -> dict:
    """Pass rate as a function of budget 1..k, over the first n slots.

    A diagnostic. No claim is attached to its shape, and in particular a rising
    curve is a property of sampling, not evidence that anything was learned.
    """
    curve = {}
    for budget in range(1, pool.k + 1):
        outcomes = {}
        for t in pool.task_ids():
            cands = [(i, x) for i, x in pool.candidates(t) if i < budget]
            outcomes[t] = (NO_CANDIDATE if not cands
                           else any(accept(x, t) for _, x in cands))
        graded = [v for v in outcomes.values() if v != NO_CANDIDATE]
        hits = sum(1 for v in graded if v is True)
        lo, hi = _wilson(hits, len(graded))
        curve[budget] = {"passes": hits, "graded": len(graded),
                         "pass_rate": round(hits / len(graded), 6) if graded else 0.0,
                         "wilson_95": [round(lo, 6), round(hi, 6)]}
    return {"schema": SCHEMA, "arm": "pass_at_k", "k": pool.k, "curve": curve,
            "does_not_prove": [
                "NOT_PROVES_LEARNING: a rising pass@k curve is a property of "
                "drawing more samples from a fixed policy."]}


def paired(arm_a: dict, arm_b: dict) -> dict:
    """McNemar on the discordant pairs of two arms over one pool.

    Refuses the statistic for a nested pair. A p-value on a difference that
    construction cannot make negative tests a null that was never live, and
    reporting one is the exact defect the pool was built to remove.
    """
    a, b = arm_a["arm"], arm_b["arm"]
    common = sorted(set(arm_a["outcomes"]) & set(arm_b["outcomes"]))
    pairs = [(arm_a["outcomes"][t], arm_b["outcomes"][t]) for t in common]
    pairs = [(x, y) for x, y in pairs
             if x != NO_CANDIDATE and y != NO_CANDIDATE]
    nb = sum(1 for x, y in pairs if x and not y)      # a passed, b failed
    nc = sum(1 for x, y in pairs if not x and y)      # b passed, a failed
    out = {"schema": SCHEMA, "arm_a": a, "arm_b": b, "n_paired": len(pairs),
           "a_only": nb, "b_only": nc, "discordant": nb + nc,
           "delta": round((nc - nb) / len(pairs), 6) if pairs else 0.0}
    circular = [r["arm"] for r in (arm_a, arm_b)
                if r.get("scored_by") == SELF_SCORED]
    if circular:
        out["p_exact"] = None
        out["refused"] = (
            f"SELF_SCORED_ARM: {circular} selects with the same function that "
            "scores it, so that arm cannot lose and no two-sided test on this "
            "pair is meaningful. The quantity is verified pass@k, not uplift. "
            "Pass an independently written `score` to best_of_k to make the "
            "comparison two-sided.")
        return out
    m, k = nb + nc, min(nb, nc)
    out["p_exact"] = (min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)
                      if m else 1.0)
    out["chi2_cc"] = (abs(nb - nc) - 1) ** 2 / m if m else 0.0
    return out
