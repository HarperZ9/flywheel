"""rocket falsifier — closing the loop COMPOUNDS, with honest bounds.

The rocket (closed loop) lifts the baseline each cycle and completes a dependency
chain the open loop cannot. The bounds: a fully-novel chain shows NO advantage, and
an unverified result never compounds (the gate stops the recursion). If any of these
fail, the "rocket" is a story.
"""
from harness.evolutionary_flywheel import (
    VerifiedPool, ChainTask, spin_cycle, measure_compounding, auto_retrieved)
from harness.task import load_task
from pathlib import Path

# a dependency chain: each task needs the fact the previous one produced
CHAIN = [
    ChainTask("t1", prereqs=[], produces="f1"),
    ChainTask("t2", prereqs=["f1"], produces="f2"),
    ChainTask("t3", prereqs=["f1", "f2"], produces="f3"),
    ChainTask("t4", prereqs=["f2", "f3"], produces="f4"),
]

# a fully-novel chain: no task reuses any prior fact
NOVEL = [ChainTask(f"n{i}", prereqs=[], produces=f"g{i}") for i in range(4)]


def test_closed_loop_compounds():
    r = measure_compounding(CHAIN, closed=True)
    assert r["solved"] == 4, "closed loop completes the dependency chain"
    assert r["monotone_rising"], "baseline lifts every cycle — the rocket signature"
    assert r["baseline_history"] == [1, 2, 3, 4]


def test_open_loop_stalls():
    r = measure_compounding(CHAIN, closed=False)
    assert r["solved"] == 1, "open loop solves only the prereq-free task, then stalls"
    assert r["final_baseline"] == 1 and not r["monotone_rising"]


def test_novel_chain_shows_no_compounding_advantage():
    # honest bound: no reuse -> closing the loop buys nothing
    closed = measure_compounding(NOVEL, closed=True)
    op = measure_compounding(NOVEL, closed=False)
    assert closed["solved"] == op["solved"] == 4   # both solve all; no free lunch


def test_unverified_result_does_not_compound():
    # the gate protects the rocket: if t2 fails verification, f2 never enters the
    # pool, so t3/t4 (which need f2) stall even with the loop closed.
    r = measure_compounding(CHAIN, closed=True, fail_keys={"t2"})
    assert r["solved"] == 1, "a failed gate stops the recursion, not amplifies it"
    assert r["final_baseline"] == 1


def test_auto_retrieved_closes_the_context_link(tmp_path):
    pool = VerifiedPool()
    pool.add_verified("f1", "receipt:f1")
    task = load_task(Path(__file__).parent.parent / "tasks" / "example_pass",
                     workdir=tmp_path / "w")
    t2 = auto_retrieved(pool, task, prereqs=["f1"])
    assert any(r.source == "f1" for r in t2.retrieved), "verified fact fed into next context"
