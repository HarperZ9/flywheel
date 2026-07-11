"""Falsifier for the budget-adaptive selector (harness/adaptive_select.py).

The component must: raise N (the measured lever) when the oracle-free confidence is
below threshold, stop as soon as a confident PASS appears, and recommend
ESCALATE only when the budget is exhausted below confidence. Budget accounting
must be honest (no infinite loop, no over-generation past max_n).
"""
import sys
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from harness.adaptive_select import AdaptiveSelector, budget_schedule, SCHEDULE_CAPACITY
from harness.proposer import ProposerOutput


def test_budget_schedule_unique_and_index_stable():
    for n in (4, 8, 16, 32, 64):
        sched = budget_schedule(n)
        assert len(sched) == n
        assert len(set(sched)) == n, f"duplicate (temp,seed) at n={n}"
        assert sched == budget_schedule(64)[:n], f"not index-stable at n={n}"
    assert budget_schedule(4)[0] == (0.0, 0)  # greedy baseline first


def test_budget_schedule_at_capacity_all_unique():
    sched = budget_schedule(SCHEDULE_CAPACITY)
    assert len(set(sched)) == SCHEDULE_CAPACITY   # exactly full, no dups


def test_budget_schedule_over_capacity_raises():
    with pytest.raises(ValueError):
        budget_schedule(SCHEDULE_CAPACITY + 1)     # would repeat pairs -> refuse


def test_adaptive_selector_rejects_max_n_over_capacity():
    with pytest.raises(ValueError):
        AdaptiveSelector(CyclingProposer(["x"]), max_n=SCHEDULE_CAPACITY + 1)


class OneCandidateProposer:
    """Always returns the same candidate text. NOTE: identical candidates are
    now gated as wrong-attractor convergence on the oracle-free path, so this
    only reaches a consensus PASS via an oracle."""
    model_ref = "stub"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(self.text, self.model_ref, seed, "h", "stub")


# textually-diverse but behaviorally-identical correct implementations of f(a)=a+1
DIVERSE_CORRECT = [
    "def f(a):\n    return a + 1\n",
    "def f(a):\n    total = a\n    total = total + 1\n    return total\n",
    "def f(a):\n    return sum((a, 1))\n",
    "def f(a):\n    x = 1\n    return a + x\n",
]


class DiverseCorrectProposer:
    """Cycles through textually-diverse but behaviorally-identical candidates --
    genuine independent agreement that should earn a confident consensus PASS."""
    model_ref = "stub"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = DIVERSE_CORRECT[self.calls % len(DIVERSE_CORRECT)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class CyclingProposer:
    """Returns candidates from a list, cycling -- lets us script multiplicity."""
    model_ref = "stub"

    def __init__(self, texts):
        self.texts = texts
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = self.texts[self.calls % len(self.texts)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class FakeOracle:
    def __init__(self, marker):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


TASK = SimpleNamespace(prompt="solve", max_new_tokens=64, system="")
SIG = "def f(a):\n    return a + 1\n"
GOOD = "def f(a):\n    return a + 1\n"
WRONG = "def f(a):\n    return a - 1\n"


def test_oracle_pass_stops_at_initial_budget():
    prop = OneCandidateProposer(GOOD)
    sel = AdaptiveSelector(prop, initial_n=4, max_n=32)
    res = sel.select(TASK, solution_sig=SIG, oracle=FakeOracle("+ 1"))
    assert res.receipt.verdict == "PASS"
    assert res.receipt.method == "oracle"
    assert res.budget_spent == 4     # passed on first round, no raise
    assert res.raises == 0


def test_consensus_majority_passes_without_oracle():
    prop = DiverseCorrectProposer()     # diverse-but-agreeing -> genuine consensus
    sel = AdaptiveSelector(prop, initial_n=4, max_n=32)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.method == "consensus"
    assert res.receipt.verdict == "CONSENSUS_PASS"   # agreement, not oracle-verified
    assert res.receipt.confidence == 1.0
    assert res.receipt.correlation < 0.85     # independent agreement, not repetition
    assert res.budget_spent == 4


def test_identical_candidates_do_not_earn_consensus():
    # 4 identical candidates agree perfectly but are not INDEPENDENT -> gated ->
    # the loop keeps raising N and ultimately escalates (no confident local accept)
    prop = OneCandidateProposer(GOOD)
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.verdict == "ESCALATE"
    assert res.raises >= 1


def test_low_confidence_raises_then_escalates():
    # every candidate behaves differently -> confidence can never reach 0.5;
    # the loop must raise N up to max_n, then recommend ESCALATE.
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    prop = CyclingProposer(distinct)
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.verdict == "ESCALATE"
    assert res.raises >= 1
    assert res.budget_spent == 16          # stopped exactly at max_n
    assert prop.calls == 16                 # no over-generation
    assert len(res.trail) >= 2              # multiple rounds recorded


def test_never_exceeds_max_n():
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(100)]
    prop = CyclingProposer(distinct)
    sel = AdaptiveSelector(prop, initial_n=3, max_n=13)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.budget_spent <= 13
    assert prop.calls <= 13


def test_trail_records_each_round():
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    prop = CyclingProposer(distinct)
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    ns = [row["n"] for row in res.trail]
    assert ns == sorted(ns)                 # monotonically growing budget
    assert ns[-1] == res.budget_spent


# --- hardening -----------------------------------------------------------------

class RaisingProposer:
    model_ref = "stub"

    def __init__(self, fail_after=0):
        self.fail_after = fail_after
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        if self.calls >= self.fail_after:
            raise RuntimeError("proposer down")
        self.calls += 1
        return ProposerOutput("def f(a):\n    return a\n", self.model_ref, seed, "h", "stub")


def test_escalate_clears_accepted_text_keeps_best_effort():
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    prop = CyclingProposer(distinct)
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.verdict == "ESCALATE"
    assert res.text is None                 # no accepted answer travels with ESCALATE
    assert res.best_effort_text is not None  # the attempt is preserved for the ledger


def test_proposer_error_escalates_no_crash():
    prop = RaisingProposer(fail_after=0)    # raises on the very first call
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.verdict == "ESCALATE"
    assert res.budget_spent == 0
    assert res.text is None


def test_proposer_error_midway_uses_what_it_has():
    prop = RaisingProposer(fail_after=2)    # 2 candidates then dies
    sel = AdaptiveSelector(prop, initial_n=4, max_n=16)
    res = sel.select(TASK, solution_sig=SIG)
    assert res.receipt.verdict in ("ESCALATE", "PASS")   # never crashes
    assert res.budget_spent <= 2

def test_none_text_from_proposer_coerced():
    class NoneTextProposer:
        model_ref = "stub"
        def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
            return ProposerOutput(None, self.model_ref, seed, "h", "stub")
    sel = AdaptiveSelector(NoneTextProposer(), initial_n=4, max_n=8)
    res = sel.select(TASK, solution_sig=SIG)   # must not crash on None text
    assert res.receipt.verdict in ("ESCALATE", "LOW_CONFIDENCE", "PASS")
