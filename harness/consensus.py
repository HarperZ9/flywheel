"""consensus.py — non-learned verifier ensembling and stability replay.

Combining several INDEPENDENT, non-learned checks beats any single verifier
(Weaver / FUSE / BoN-MAV, 2025): a wrong answer must fool all of them, not one.
Flywheel's Oracle protocol makes this a pure composition. Each member still
accepts on its own falsifiable check, and the combiner is fixed arithmetic a
third party re-runs, so the C2 invariant (no learned model on the accept path)
holds and the verdict stays re-checkable. The receipt hash folds every member's
verdict, so a stranger reproduces the combined decision offline.

- ConsensusOracle: run N member oracles, accept per a fixed rule (all / any /
  majority / weighted-threshold).
- RepeatConsistencyOracle: run one oracle k times and require a STABLE, agreeing
  pass. A flaky / nondeterministic "pass" (order-dependent shortcut, timing race)
  is refused. Isomorphic-perturbation replay, non-learned.
"""
from __future__ import annotations

import hashlib
import json

from .integrity import GuardedOracle
from .oracle import OracleResult, PytestOracle

_RULES = ("all", "any", "majority", "weighted")


class ConsensusOracle:
    """Accept only when N independent member oracles agree per a fixed rule.

    rule="all" is the strongest and the natural way to add a held-out check on top
    of the visible suite (accept iff BOTH pass). "majority" and "weighted" trade
    strictness for robustness to one flaky member. Nothing learned decides; the
    rule is arithmetic over the members' own falsifiable verdicts."""

    def __init__(self, members, *, rule: str = "all", threshold: float = 0.5,
                 weights=None):
        members = list(members)
        if not members:
            raise ValueError("ConsensusOracle needs at least one member oracle")
        if rule not in _RULES:
            raise ValueError(f"rule must be one of {_RULES}")
        if weights is not None and len(weights) != len(members):
            raise ValueError("weights must match members length")
        self.members = members
        self.rule = rule
        self.threshold = threshold
        self.weights = [float(w) for w in weights] if weights else [1.0] * len(members)
        self.oracle_type = "consensus:" + "+".join(
            getattr(m, "oracle_type", "?") for m in members)

    def _decide(self, passes: list) -> bool:
        n = len(passes)
        if self.rule == "all":
            return all(passes)
        if self.rule == "any":
            return any(passes)
        if self.rule == "majority":
            return sum(1 for p in passes if p) * 2 > n
        wsum = sum(self.weights) or 1.0
        score = sum(w for w, p in zip(self.weights, passes) if p) / wsum
        return score >= self.threshold

    def verify(self, candidate: str, task) -> OracleResult:
        results = [m.verify(candidate, task) for m in self.members]
        passes = [r.passed for r in results]
        decided = self._decide(passes)
        rows = sorted([getattr(m, "oracle_type", "?"), bool(r.passed), r.output_hash]
                      for m, r in zip(self.members, results))
        preimage = json.dumps([self.rule, self.threshold, rows], sort_keys=True)
        digest = hashlib.sha256(preimage.encode()).hexdigest()[:16]
        summary = "; ".join(f"{ot}={'PASS' if p else 'FAIL'}" for ot, p, _ in rows)
        return OracleResult(
            passed=decided, cmd=self.oracle_type, output_hash=digest,
            stdout_excerpt=f"[consensus:{self.rule}] {summary}",
            rc=0 if decided else 1)


class RepeatConsistencyOracle:
    """Run one oracle k times; accept only on a STABLE agreeing pass. If the runs
    disagree (same candidate, different verdict or different canonical output),
    the pass is flaky and is refused. Catches order-dependent shortcuts and timing
    races that a single run would accept. Non-learned."""

    def __init__(self, base, *, runs: int = 2):
        if runs < 2:
            raise ValueError("runs must be >= 2 to check consistency")
        self.base = base
        self.runs = runs
        self.oracle_type = f"repeat{runs}:{getattr(base, 'oracle_type', '?')}"

    def verify(self, candidate: str, task) -> OracleResult:
        results = [self.base.verify(candidate, task) for _ in range(self.runs)]
        all_pass = all(r.passed for r in results)
        stable = len({r.output_hash for r in results}) == 1
        passed = all_pass and stable
        preimage = "|".join(sorted(f"{r.passed}:{r.output_hash}" for r in results))
        digest = hashlib.sha256(preimage.encode()).hexdigest()[:16]
        if all_pass and not stable:
            note = (f"[repeat] nondeterministic: "
                    f"{len({r.output_hash for r in results})} distinct outcomes over {self.runs} runs")
        else:
            note = f"[repeat] {sum(1 for r in results if r.passed)}/{self.runs} pass, stable={stable}"
        return OracleResult(passed=passed, cmd=self.oracle_type, output_hash=digest,
                            stdout_excerpt=note, rc=0 if passed else 1)


def accept_gate(task, *, timeout: int = 60, guard: bool = True):
    """The strongest non-learned accept gate for a task: the visible test suite,
    AND (when the task carries one) a HELD-OUT check the model never saw, must both
    pass -- ConsensusOracle rule="all" -- and a candidate that tampered with the
    check is refused (GuardedOracle). Every member is falsifiable and re-checkable;
    nothing learned decides.

    Held-out verification counters the measured failure mode where a model games a
    weak or leaked visible suite (UTBoost; SpecBench). The held-out command's test
    files are simply not provided to the model, so it cannot fit to them."""
    visible = PytestOracle(timeout=timeout)
    if getattr(task, "held_out_cmd", ""):
        base = ConsensusOracle(
            [visible, PytestOracle(timeout=timeout, cmd_attr="held_out_cmd")], rule="all")
    else:
        base = visible
    return GuardedOracle(base) if guard else base
