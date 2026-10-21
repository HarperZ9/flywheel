"""Flywheel's arms of the ledger-quirks head-to-head.

flywheel_gated     the shipped design: grader-free Propose-Probe-Compose per
                   task, carry-over only through the held-out gate.
flywheel_ungated   the same loop with the gate switched off, so the chosen
                   harness always becomes the next incumbent. It isolates the
                   gate's contribution from the rest of the loop.
base               the base harness, no loop.

Every arm reports per-task rows: the delivered output's grade, whether the
delivering harness carries a gaming or harmful feature, and executions spent.
"""
from __future__ import annotations

from harness import self_improve_bench as bench
from harness.self_improve_adapters import CallableExecutor, ContrastSelector
from harness.self_improve_bench_agents import ScriptedEditor, planted_edits
from harness.self_improve_controls import run_controls
from harness.self_improve_gate import GatePolicy, HeldOutGate
from harness.self_improve_loop import run_task
from harness.self_improve_stream import Stream, StreamConfig

BAD = set(bench.HARMFUL) | set(bench.GAMING)


def _row(arm, cell, phase, task, output, feats, executions) -> dict:
    graded = bench.grade(task, bench.Rollout("x", output))
    return {"arm": arm, **cell, "phase": phase, "task_id": task["id"], "score": graded,
            "poisoned": bool(feats & BAD), "features": sorted(feats),
            "executions": executions}


def base_rows(cell: dict, tasks: list[dict], phase: str) -> list[dict]:
    tree = bench.base_tree()
    return [_row("base", cell, phase, t, bench.execute(t, tree, "b").output, set(), 1)
            for t in tasks]


def flywheel_rows(cell: dict, splits: dict, *, gated: bool) -> tuple[list[dict], dict]:
    arm = "flywheel_gated" if gated else "flywheel_ungated"
    executor = CallableExecutor(bench.execute)
    editor = ScriptedEditor(seed=cell["seed"], p_game=cell["p_game"])
    selector = ContrastSelector(bench.contrast_score)
    gate = HeldOutGate(splits["gate"], bench.grade, executor, GatePolicy(seed=cell["seed"]))
    stream = Stream(executor, editor, selector, gate, bench.base_tree(),
                    StreamConfig(mode=cell["mode"], k=cell["k"], gate_enabled=gated))
    rows, spent = [], 0
    for task in splits["stream"]:
        before = gate.executions
        r = stream.step(task)
        cost = r["budget"]["rollouts"] + (gate.executions - before)
        spent += cost
        tree = stream.last_run.chosen_tree()
        rows.append(_row(arm, cell, "stream", task, r["output"], bench.features_of(tree), cost))
    frozen = stream.library.incumbent()
    for task in splits["test"]:
        run = run_task(task, mode=cell["mode"], k=cell["k"], incumbent=frozen,
                       executor=executor, editor=editor, selector=selector)
        rows.append(_row(arm, cell, "test", task, run.rollouts[run.chosen].output,
                         bench.features_of(run.chosen_tree()), run.budget["rollouts"]))
        rows.append(_row(arm + "_incumbent", cell, "test", task,
                         bench.execute(task, frozen, "i").output,
                         bench.features_of(frozen), 1))
    summary = {"arm": arm, **cell, "adoptions": sum(r["decision"] == "ADOPT"
                                                   for r in stream.rows),
               "final_features": sorted(bench.features_of(frozen)),
               "stream_executions": spent, "library_chain_ok": stream.library.verify_chain()}
    return rows, summary


def control_report(cell: dict, splits: dict) -> dict:
    """The planted-edit suite against the base harness, on this seed's gate set."""
    gate = HeldOutGate(splits["gate"], bench.grade, CallableExecutor(bench.execute),
                       GatePolicy(seed=cell["seed"]))
    report = run_controls(gate, bench.base_tree(),
                          planted_edits(bench.base_tree(), splits["stream"][0]))
    return {**cell, "verdict": report["verdict"], "false_accepts": report["false_accepts"],
            "false_rejects": report["false_rejects"],
            "controls": [{k: c[k] for k in ("name", "kind", "expect", "got", "ok",
                                             "adopted_components")}
                         for c in report["controls"]]}
