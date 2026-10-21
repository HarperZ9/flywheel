"""Harness-squared's arm of the ledger-quirks head-to-head (needs a harness2 checkout).

The stream runs task by task through harness2.core.schedule.run_task with a
per-mode Library, retaining earlier entries the way run_domain does. The test
tasks then run against the library frozen at the end of the stream: each test
task's own entry is removed again before the next one starts.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from harness2.core import library as library_store
from harness2.core import schedule

from harness import self_improve_bench as bench
from harness.self_improve_bench_agents import ScriptedEditor

from flywheel_arm import _row
from h2_ledger_quirks import LedgerAdapter, ScriptedProposer, flywheel_tree

MODE_TOKEN = {"parallel": "agg", "sequential": "seq"}


def h2_rows(cell: dict, splits: dict, *, carry: float) -> list[dict]:
    arm = f"harness2_c{carry:.2f}"
    mode = MODE_TOKEN[cell["mode"]]
    with tempfile.TemporaryDirectory(prefix="h2-ledgerq-") as tmp:
        root = Path(tmp)
        adapter = LedgerAdapter(root, splits["stream"] + splits["test"])
        editor = ScriptedEditor(seed=cell["seed"], p_game=cell["p_game"])
        prop = ScriptedProposer(adapter.spec.channels["proposer"], adapter, editor, carry)
        surface = adapter.substrate.surface()
        lib = library_store.Library(root=root / "library" / mode, domain="ledger",
                                    surface=surface)
        rows, done = [], []
        for phase in ("stream", "test"):
            for task in splits[phase]:
                lib.retain(done)
                before = _executions(root)
                res = schedule.run_task(task["id"], cell["k"], adapter=adapter, prop=prop,
                                        runs_root=root / "runs" / phase, modes=(mode,),
                                        seed=cell["seed"], libraries={mode: lib})
                output, feats = _delivered_from(adapter, res, mode, root / "runs" / phase)
                rows.append(_row(arm, cell, phase, task, output, feats,
                                 _executions(root) - before))
                if phase == "stream":
                    done.append(task["id"])
        return rows


def _executions(root: Path) -> int:
    d = root / "executions"
    return sum(1 for _ in d.rglob("answer.txt")) if d.is_dir() else 0


def _delivered_from(adapter, res, mode: str, runs_root: Path) -> tuple[str, set[str]]:
    sel = res.selections.get(mode, {})
    run_dir = Path(sel.get("chosen_run_dir") or "")
    if not sel.get("chosen_run_dir") or not run_dir.is_dir():
        return "", set()
    label = sel.get("chosen_label", "")
    hits = sorted(runs_root.glob(f"*/{res.task_id}/harnesses/{label}"))
    feats = bench.features_of(flywheel_tree(hits[0])) if hits else set()
    return adapter.deliverable_text(run_dir), feats


