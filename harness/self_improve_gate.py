"""self_improve_gate.py -- the held-out gate a harness edit must pass to persist.

The task-level loop chooses an edit from behavioural contrast alone. That
choice can serve the task in hand. It may not change what every later task
starts from until it has earned that on a graded set the editor and the
selector never saw.

The gate is paired: the incumbent and the candidate run on the same held-out
tasks, and the per-task difference carries the interval (a bootstrap over
tasks, through statistics.cluster_bootstrap). Each changed component is also
measured by leaving it out of the candidate. A component whose removal costs
nothing on the held-out set is dropped from the adopted edit, so an edit to the
harness's self-check cannot ride into the persistent harness on the back of a
real fix.

What a pass does not prove is stated on the result, because a small held-out
set is a sample: it bounds the effect on that distribution, not on tasks
unlike it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import self_improve_tree as st
from .evidence_json import canonical_sha256
from .self_improve_loop import Executor, Rollout
from .statistics import cluster_bootstrap

Grader = Callable[[dict, Rollout], float]
ADOPT, REJECT = "ADOPT", "REJECT"


@dataclass
class GatePolicy:
    alpha: float = 0.10          # two-sided interval level is 1 - alpha
    min_point: float = 0.0       # the mean paired difference must exceed this
    min_lower: float = 0.0       # the interval's lower bound must reach this
    draws: int = 2000
    seed: int = 0
    attribute: bool = True       # measure each changed component alone


@dataclass
class HeldOutGate:
    tasks: list[dict]
    grader: Grader
    executor: Executor
    policy: GatePolicy = field(default_factory=GatePolicy)
    executions: int = 0
    _cache: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.tasks) < 2:
            raise ValueError("a held-out gate needs at least two graded tasks")
        ids = [str(t.get("id", "")) for t in self.tasks]
        if len(set(ids)) != len(ids) or not all(ids):
            raise ValueError("held-out tasks need unique, non-empty ids")

    @property
    def set_digest(self) -> str:
        """Binds the gate to its exact tasks, answers included."""
        return canonical_sha256(self.tasks)

    def scores(self, tree: st.Tree) -> list[float]:
        key = st.digest(tree)
        if key not in self._cache:
            out = []
            for task in self.tasks:
                self.executions += 1
                try:
                    rollout = self.executor.execute(task, tree, f"gate:{task['id']}")
                except Exception as exc:  # a crashed rollout scores zero, on the record
                    rollout = Rollout("gate", "", delivered=False, error=str(exc))
                out.append(float(self.grader(task, rollout)) if rollout.delivered else 0.0)
            self._cache[key] = out
        return self._cache[key]

    def effect(self, incumbent: st.Tree, candidate: st.Tree) -> dict:
        """Paired held-out effect of candidate over incumbent, with its interval."""
        a, b = self.scores(incumbent), self.scores(candidate)
        diffs = {str(t["id"]): [cb - ca] for t, ca, cb in zip(self.tasks, a, b)}
        boot = cluster_bootstrap(diffs, lambda u: sum(u) / len(u), draws=self.policy.draws,
                                 seed=self.policy.seed, alpha=self.policy.alpha)
        point = sum(b) / len(b) - sum(a) / len(a)
        return {"n": len(a), "incumbent_mean": round(sum(a) / len(a), 6),
                "candidate_mean": round(sum(b) / len(b), 6), "point": round(point, 6),
                "interval": boot["interval"], "alpha": self.policy.alpha,
                "method": "paired bootstrap over held-out tasks",
                "wins": sum(1 for x, y in zip(a, b) if y > x),
                "losses": sum(1 for x, y in zip(a, b) if y < x),
                "set_digest": self.set_digest}

    def passes(self, eff: dict) -> bool:
        return (eff["point"] > self.policy.min_point
                and eff["interval"][0] >= self.policy.min_lower)

    def _attribute(self, incumbent: st.Tree, candidate: st.Tree,
                   components: list[str]) -> list[dict]:
        """Leave-one-out: a component earns its place if removing it from the
        candidate costs held-out score. Measuring against the full candidate,
        not the incumbent, keeps fixes that only pay off together."""
        rows = []
        for comp in components:
            others = [c for c in components if c != comp]
            without = st.restrict(incumbent, candidate, others)
            eff = self.effect(without, candidate)
            rows.append({"component": comp, "verification_surface":
                         st.touches_verification([comp]), "effect": eff,
                         "kept": self.passes(eff)})
        return rows

    def review(self, incumbent: st.Tree, candidate: st.Tree) -> dict:
        """Decide whether (part of) candidate becomes the new incumbent."""
        components = st.changed_components(incumbent, candidate)
        if not components:
            return _result(REJECT, incumbent, [], None, [], "no change to review", self)
        rows: list[dict] = []
        keep = components
        if self.policy.attribute or st.touches_verification(components):
            rows = self._attribute(incumbent, candidate, components)
            keep = [r["component"] for r in rows if r["kept"]]
        if not keep:
            return _result(REJECT, incumbent, [], None, rows,
                           "no component earned its place on the held-out set", self)
        adopted = st.restrict(incumbent, candidate, keep)
        eff = self.effect(incumbent, adopted)
        if not self.passes(eff):
            return _result(REJECT, incumbent, [], eff, rows,
                           "the kept components together did not pass", self)
        return _result(ADOPT, adopted, keep, eff, rows, "passed the held-out gate", self)


def _result(decision: str, tree: st.Tree, kept: list[str], eff: dict | None,
            rows: list[dict], reason: str, gate: HeldOutGate) -> dict:
    return {"decision": decision, "reason": reason, "adopted_components": kept,
            "tree": tree, "heldout": eff, "attribution": rows,
            "gate_executions": gate.executions,
            "policy": {"alpha": gate.policy.alpha, "min_point": gate.policy.min_point,
                       "min_lower": gate.policy.min_lower, "draws": gate.policy.draws},
            "does_not_prove": [
                "the held-out effect bounds this set's task distribution only",
                "a bootstrap over tasks omits between-seed variance of the executor",
                "a pass does not show the edit is safe outside the graded criterion",
            ]}
