"""self_improve_gate.py -- the held-out gate a harness edit must pass to persist.

The task-level loop chooses an edit from behavioural contrast alone. That
choice can serve the task in hand. It may not change what every later task
starts from until it has earned that on a graded set the editor and the
selector never saw.

The gate is paired: the incumbent and the candidate run on the same held-out
tasks, and the per-task difference carries the interval (a bootstrap over
tasks, through statistics.cluster_bootstrap). Each changed component is also
measured by leaving it out of the candidate, down to single changed lines
(self_improve_units.py). A unit whose removal costs nothing on the held-out set
is dropped from the adopted edit, so a self-check edit or a wrong line cannot
ride into the persistent harness on the back of a real fix.

What a pass covers is stated on the result as its `scope`, because a small
held-out set is a sample: it bounds the effect on that distribution, and tasks
unlike it sit outside the bound.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import self_improve_tree as st
from . import self_improve_units as su
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
    attribute: bool = True       # leave each change unit out of the candidate
    granularity: str = "line"    # finest unit tried: line, hunk or file
    max_units: int = 24          # split a kept hunk into lines only up to this size


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

    def _loo(self, incumbent: st.Tree, candidate: st.Tree, fixed: list[str],
             units: list[str], level: str) -> list[dict]:
        """Leave-one-out over units with `fixed` always applied: a unit earns its
        place if removing it costs held-out score. Measuring against the full
        candidate, not the incumbent, keeps changes that only pay off together."""
        full = su.apply_units(incumbent, candidate, fixed + units)
        rows = []
        for unit in units:
            others = fixed + [u for u in units if u != unit]
            eff = self.effect(su.apply_units(incumbent, candidate, others), full)
            comp = su.unit_component(unit)
            rows.append({"unit": unit, "component": comp, "level": level,
                         "verification_surface": st.touches_verification([comp]),
                         "effect": eff, "kept": self.passes(eff)})
        return rows

    def _attribute(self, incumbent: st.Tree, candidate: st.Tree) -> tuple[list, list]:
        """Files first, then hunks inside kept files, then lines inside kept hunks.

        Going coarse to fine means a line is tested only inside a file and a
        hunk that already earned their place, so a partial rewrite that no
        longer runs cannot keep a file the gate would have dropped whole.
        """
        tree = su.unit_tree(incumbent, candidate)
        rows = self._loo(incumbent, candidate, [], [f for f, _ in tree], "file")
        kept_files = {r["unit"] for r in rows if r["kept"]}
        if self.policy.granularity == "file":
            return rows, sorted(kept_files)
        whole_files = [f for f, hunks in tree if f in kept_files and not hunks]
        hunks = [h for f, hs in tree if f in kept_files for h, _ in hs]
        hrows = self._loo(incumbent, candidate, whole_files, hunks, "hunk")
        kept_h = [r["unit"] for r in hrows if r["kept"]]
        if self.policy.granularity == "hunk":
            return rows + hrows, whole_files + kept_h
        lines_of = {h: ls for _, hs in tree for h, ls in hs}
        split = [h for h in kept_h if 1 < len(lines_of[h]) <= self.policy.max_units]
        fixed = whole_files + [h for h in kept_h if h not in split]
        lrows = self._loo(incumbent, candidate, fixed,
                          [ln for h in split for ln in lines_of[h]], "line")
        return rows + hrows + lrows, fixed + [r["unit"] for r in lrows if r["kept"]]

    def review(self, incumbent: st.Tree, candidate: st.Tree) -> dict:
        """Decide whether (part of) candidate becomes the new incumbent."""
        components = st.changed_components(incumbent, candidate)
        gran = self.policy.granularity
        if not components:
            return _result(REJECT, incumbent, [], None, [], "no change to review", self, gran)
        if gran not in su.GRANULARITIES:
            raise ValueError(f"granularity must be one of {su.GRANULARITIES}")
        if self.policy.attribute or st.touches_verification(components):
            rows, keep = self._attribute(incumbent, candidate)
        else:
            rows, keep = [], [f for f, _ in su.unit_tree(incumbent, candidate)]
        adopted = su.apply_units(incumbent, candidate, keep)
        if not keep or adopted == incumbent:
            return _result(REJECT, incumbent, [], None, rows,
                           "no change unit earned its place on the held-out set", self, gran)
        eff = self.effect(incumbent, adopted)
        if not self.passes(eff):
            return _result(REJECT, incumbent, [], eff, rows,
                           "the kept units together did not pass", self, gran)
        return _result(ADOPT, adopted, keep, eff, rows, "passed the held-out gate", self, gran)


def _result(decision: str, tree: st.Tree, kept: list[str], eff: dict | None,
            rows: list[dict], reason: str, gate: HeldOutGate, gran: str = "") -> dict:
    return {"decision": decision, "reason": reason,
            "adopted_components": sorted({su.unit_component(u) for u in kept}),
            "adopted_units": list(kept), "granularity": gran, "tree": tree,
            "heldout": eff, "attribution": rows,
            "gate_executions": gate.executions,
            "policy": {"alpha": gate.policy.alpha, "min_point": gate.policy.min_point,
                       "min_lower": gate.policy.min_lower, "draws": gate.policy.draws},
            "scope": [
                "the held-out effect bounds this set's task distribution only",
                "the bootstrap runs over tasks; between-seed variance of the executor "
                "sits outside it",
                "a pass covers the graded criterion; the edit's safety beyond it is "
                "a separate check",
            ]}
