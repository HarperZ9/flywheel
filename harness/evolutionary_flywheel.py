"""evolutionary_flywheel.py — close memory->context and measure COMPOUNDING.

The trampoline is a static bounded multiplier: amplitude = prod(amplifiers) *
prod(gates), one bounce. The ROCKET is temporal recursion: a CLOSED feedback loop
where cycle n's VERIFIED output raises cycle n+1's baseline, so capability compounds
over cycles. This module closes the memory->context link (auto_retrieved) and
measures whether closing it actually compounds — the falsifiable rocket signature.

The load-bearing honesty, all test-enforced:
  1. Compounding needs REUSE. A dependency chain (task k needs facts from 1..k-1)
     compounds when the loop is closed and STALLS when open. A fully-novel chain
     (no reuse) shows NO advantage — no free lunch on genuinely new work.
  2. Only VERIFIED results compound. An unverified result never enters the pool, so
     a failed gate stops the recursion instead of amplifying a hallucination. The
     gates are the rocket's safety: you cannot compound your way up on errors.
  3. The ceiling is the novel core. Once the shared facts are established, only the
     irreducible novel work costs — compounding is bounded, not perpetual-motion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .task import Task, Retrieved


@dataclass
class VerifiedPool:
    """The growing store of VERIFIED facts — the closed memory the next cycle draws
    on. Only verified results enter; unverified ones cannot compound."""
    facts: dict[str, str] = field(default_factory=dict)   # key -> receipt
    baseline_history: list[int] = field(default_factory=list)

    def add_verified(self, key: str, receipt: str) -> None:
        self.facts[key] = receipt

    def baseline(self) -> int:
        return len(self.facts)

    def context_for(self, prereqs: list[str]) -> list[Retrieved]:
        return [Retrieved(source=k, receipt=self.facts[k]) for k in prereqs if k in self.facts]


def auto_retrieved(pool: VerifiedPool, task: Task, prereqs: list[str]) -> Task:
    """Close the memory->context link: populate a task's retrieved context from the
    VERIFIED pool. This is the feedback edge that turns the trampoline into a rocket
    — a verified fact from a prior cycle becomes available to the next proposal."""
    from dataclasses import replace
    return replace(task, retrieved=pool.context_for(prereqs))


@dataclass
class ChainTask:
    key: str
    prereqs: list[str]          # verified facts this task needs in context
    produces: str               # the fact it establishes when it passes


def spin_cycle(pool: VerifiedPool, t: ChainTask, *, closed: bool,
               verifies: bool = True) -> dict:
    """One cycle. closed=True feeds context from the pool; open=False does not. A
    task is solvable iff its prereqs are present AND it verifies. On a verified
    pass its produced fact enters the pool (raising the next baseline)."""
    ctx = pool.context_for(t.prereqs) if closed else []
    have_prereqs = len(ctx) == len(t.prereqs)
    passed = have_prereqs and verifies
    if passed:
        pool.add_verified(t.produces, f"receipt:{t.produces}")
    pool.baseline_history.append(pool.baseline())
    return {"key": t.key, "passed": passed, "baseline": pool.baseline(),
            "had_context": have_prereqs}


def measure_compounding(chain: list[ChainTask], *, closed: bool,
                        fail_keys: set[str] | None = None) -> dict:
    """Run a chain closed or open. Returns solved count, whether the baseline lifted
    monotonically (the rocket signature), and the per-cycle trace. fail_keys marks
    tasks whose verification FAILS (their fact must not compound)."""
    fail_keys = fail_keys or set()
    pool = VerifiedPool()
    trace = [spin_cycle(pool, t, closed=closed, verifies=(t.key not in fail_keys))
             for t in chain]
    hist = pool.baseline_history
    monotone_rising = all(b >= a for a, b in zip(hist, hist[1:])) and hist[-1] > hist[0] if len(hist) > 1 else False
    return {"solved": sum(1 for r in trace if r["passed"]),
            "n": len(chain), "final_baseline": pool.baseline(),
            "baseline_history": hist, "monotone_rising": monotone_rising,
            "trace": trace}
