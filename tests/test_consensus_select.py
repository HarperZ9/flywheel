"""consensus_select contract — the oracle-free behavioral selector must pick
the majority-behavior candidate, and must never lose the single-shot passer.

This is the load-bearing property of the verified_consensus arm: the model
authors nothing; selection is by behavioral agreement on a pre-decided input
battery. If a wrong plurality could displace a lone correct temp-0 candidate,
the arm would report false losses; the tie-break to index 0 prevents that.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "run_ablation", Path(__file__).resolve().parent.parent / "scripts" / "run_ablation.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)


GOOD = "def f(a):\n    return a + 1\n"          # canonical behavior
GOOD2 = "def f(a):\n    return 1 + a\n"         # same behavior, different text
WRONG = "def f(a):\n    return a - 1\n"         # different behavior
BROKEN = "def f(a):\n    return undefined_name\n"  # raises on every input


def test_majority_behavior_wins(tmp_path):
    # 3 agree (GOOD/GOOD2/GOOD2), 1 disagrees (WRONG) -> pick from the majority
    idx = ra.consensus_select([WRONG, GOOD, GOOD2, GOOD2], "f", 1, tmp_path)
    assert idx in (1, 2, 3)  # a member of the 3-candidate GOOD cluster


def test_tie_breaks_to_index_zero(tmp_path):
    # two clusters of equal size (GOOD,GOOD2) vs (WRONG,WRONG2); the cluster
    # containing index 0 must win, protecting the single-shot passer at [0]
    WRONG2 = "def f(a):\n    return a - 1  # dup\n"
    idx = ra.consensus_select([GOOD, WRONG, GOOD2, WRONG2], "f", 1, tmp_path)
    assert idx == 0


def test_broken_candidate_never_forms_majority(tmp_path):
    # one real answer + broken siblings that each fail to run -> the runnable
    # one is its own cluster; broken ones get unique signatures, never cluster
    idx = ra.consensus_select([GOOD, BROKEN, BROKEN], "f", 1, tmp_path)
    # GOOD is a singleton cluster (size 1); the two BROKEN are unique singletons
    # too -> tie among size-1 clusters, tie-break to lowest index = 0 (GOOD)
    assert idx == 0


def test_battery_matches_arity():
    b1 = ra._battery(1)
    b2 = ra._battery(2)
    assert all(len(t) == 1 for t in b1)
    assert all(len(t) == 2 for t in b2)
