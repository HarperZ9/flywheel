"""adaptive_select.py -- budget-adaptive selection: RAISE N until confident.

The measured lever (2026-07-10 pass@N curve): oracle-free consensus is bounded by
candidate MULTIPLICITY, and raising N moves tasks across the >=2-correct
threshold (topo_sort 0/8 -> 3/16 correct; sliding_window_max 1/4 -> 18/32). This
component owns a proposer and a budget and implements the loop that finding
justifies: generate a batch, select over the pool, and if the verdict is not a
confident PASS and budget remains, DOUBLE N and re-select. Only when the budget
is exhausted below confidence does it recommend ESCALATE -- the companion-seat
decision (answer locally vs route to a costlier external-oracle/frontier tier),
made on evidence, not a learned difficulty guess.

No learned model sits in the accept path: an external oracle decides when
present, otherwise deterministic behavioral consensus decides, and the escalate
recommendation is a thresholded confidence, not a prediction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .proposer import Proposer
from .task import Task
from .oracle import Oracle
from .selector import select, SelectionResult, SelectionReceipt, ACCEPT_VERDICTS

# Unique (temperature, seed) grid, INDEX-STABLE so a raise only generates the new
# tail. Index 0 is the greedy baseline (temp 0 is deterministic -> appears once).
# 9 hot temps x 8 seeds = 72 unique hot pairs -> supports N up to 73.
_HOT_TEMPS = [0.2, 0.35, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]
_SEEDS = [0, 42, 137, 7, 2024, 99, 314, 11]
SCHEDULE_CAPACITY = 1 + len(_HOT_TEMPS) * len(_SEEDS)   # 73 unique pairs


def budget_schedule(n: int) -> list[tuple[float, int]]:
    """n (temperature, seed) pairs, all unique, index-stable across n. Raises if
    n exceeds SCHEDULE_CAPACITY -- past that the grid would repeat pairs and the
    'more N = more diversity' guarantee would silently break."""
    if n > SCHEDULE_CAPACITY:
        raise ValueError(
            f"budget_schedule({n}) exceeds capacity {SCHEDULE_CAPACITY}; "
            f"more candidates would repeat (temp, seed) pairs and add no diversity")
    out = [(0.0, 0)]
    for i in range(n - 1):
        out.append((_HOT_TEMPS[i % len(_HOT_TEMPS)],
                    _SEEDS[(i // len(_HOT_TEMPS)) % len(_SEEDS)]))
    return out[:n]


@dataclass
class AdaptiveResult:
    text: str | None                  # ACCEPTED answer -- None unless verdict in ACCEPT_VERDICTS
                                      # (PASS = oracle-verified, or CONSENSUS_PASS = agreement)
    receipt: SelectionReceipt
    budget_spent: int                 # candidates generated
    raises: int                       # how many times N was doubled
    trail: list[dict] = field(default_factory=list)  # per-round receipts
    best_effort_text: str | None = None  # last unverified attempt (for the ledger on ESCALATE)


class AdaptiveSelector:
    """Generate -> select -> (raise N | escalate). Composes the pure selector
    with a proposer and a budget ceiling."""

    def __init__(self, proposer: Proposer, *, initial_n: int = 4, max_n: int = 32,
                 confidence_threshold: float = 0.5):
        if initial_n < 1 or max_n < initial_n:
            raise ValueError("need 1 <= initial_n <= max_n")
        if max_n > SCHEDULE_CAPACITY:
            raise ValueError(
                f"max_n {max_n} exceeds schedule capacity {SCHEDULE_CAPACITY} "
                f"(past that, raising N repeats generations)")
        self.proposer = proposer
        self.initial_n = initial_n
        self.max_n = max_n
        self.confidence_threshold = confidence_threshold

    def select(self, task: Task, *, solution_sig: str = "",
               oracle: Oracle | None = None) -> AdaptiveResult:
        schedule = budget_schedule(self.max_n)
        candidates: list[str] = []
        trail: list[dict] = []
        raises = 0
        target = min(self.initial_n, self.max_n)

        gen_failed = False
        while True:
            for (temp, seed) in schedule[len(candidates):target]:
                try:
                    out = self.proposer.generate(
                        task.prompt, seed=seed, temperature=temp,
                        max_new_tokens=task.max_new_tokens, system=task.system)
                except Exception:
                    gen_failed = True       # a broken proposer must not crash the loop
                    break
                candidates.append(getattr(out, "text", ""))

            if not candidates:
                # proposer produced nothing -> nothing to select; escalate honestly
                return AdaptiveResult(None, SelectionReceipt(
                    method="escalate", selected_index=-1, confidence=0.0,
                    candidates_used=0, verdict="ESCALATE",
                    reason="proposer produced no candidates -- escalate",
                    task_id=getattr(task, "task_id", None)),
                    budget_spent=0, raises=raises, trail=trail)

            result = select(candidates, solution_sig=solution_sig, task=task,
                            oracle=oracle, confidence_threshold=self.confidence_threshold)
            trail.append({"n": len(candidates), **result.receipt.to_dict()})

            if result.receipt.verdict in ACCEPT_VERDICTS:   # PASS or CONSENSUS_PASS
                return AdaptiveResult(result.text, result.receipt,
                                      budget_spent=len(candidates), raises=raises,
                                      trail=trail, best_effort_text=result.text)
            if gen_failed or len(candidates) >= self.max_n:
                break
            target = min(self.max_n, max(target * 2, len(candidates) + 1))
            raises += 1

        # Budget exhausted (or proposer failed) below confidence -> escalate.
        # text is None: an ESCALATE result carries NO accepted answer. The last
        # unverified attempt travels separately as best_effort_text for the ledger.
        r = result.receipt
        r.verdict = "ESCALATE"
        r.reason = (f"budget {len(candidates)} "
                    f"{'aborted (proposer error)' if gen_failed else 'exhausted'} below "
                    f"confidence ({r.confidence:.0%} < {self.confidence_threshold:.0%}) "
                    f"after {raises} raises -- route to an external oracle / frontier tier")
        return AdaptiveResult(None, r, budget_spent=len(candidates),
                              raises=raises, trail=trail, best_effort_text=result.text)
