"""self_improve_loop.py -- task-level Propose-Probe-Compose without a grader.

This is the task-level half of a self-improving harness, built to the same
budget shape Harness-squared publishes so the two can be compared at equal
cost: each mode spends 4k rollouts and 3k editor calls.

  parallel   k reference rollouts of the incumbent; k general (INV) and k
             domain (DOM) proposals from that shared evidence; k independent
             compositions over the whole probe pool. Finals: agg1..aggk.
  sequential k steps; each proposes INV and DOM edits from the current harness,
             probes them, composes c_t over the accumulated pool, and carries
             c_t into the next step. Finals: c1..ck.

Nothing in this module grades. The task view handed to the editor and the
selector has every grader key removed, and a task that still carries one after
stripping is refused. Whether an outcome was right is the gate's business
(self_improve_gate.py), on a set this loop never sees.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from . import self_improve_tree as st

GRADER_KEYS = ("answer", "expected", "rubric", "reference_answer", "grader")
MODES = ("parallel", "sequential")


@dataclass
class Rollout:
    label: str
    output: str
    trajectory: str = ""
    delivered: bool = True
    error: str = ""


@dataclass
class EditContext:
    task: dict
    label: str
    dim: str                      # INV | DOM | COMPOSE
    current: st.Tree
    reference: list[Rollout]
    pool: list[tuple[str, st.Tree, Rollout]] = field(default_factory=list)
    lessons: list[dict] = field(default_factory=list)


@dataclass
class Proposal:
    tree: st.Tree
    notes: str = ""


class Executor(Protocol):
    def execute(self, task: dict, tree: st.Tree, label: str) -> Rollout: ...


class Editor(Protocol):
    def propose(self, ctx: EditContext) -> Proposal: ...


class Selector(Protocol):
    def choose(self, task: dict, finals: dict[str, Rollout]) -> tuple[str, str, dict]: ...


@dataclass
class TaskRun:
    task_id: str
    mode: str
    k: int
    trees: dict[str, st.Tree] = field(default_factory=dict)
    rollouts: dict[str, Rollout] = field(default_factory=dict)
    stages: list[dict] = field(default_factory=list)
    finals: list[str] = field(default_factory=list)
    chosen: str = ""
    why: str = ""
    scores: dict = field(default_factory=dict)
    budget: dict = field(default_factory=lambda: {"rollouts": 0, "edits": 0})

    def chosen_tree(self) -> st.Tree:
        return self.trees[self.chosen]

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "mode": self.mode, "k": self.k,
                "stages": self.stages, "finals": self.finals, "chosen": self.chosen,
                "why": self.why, "scores": self.scores, "budget": dict(self.budget),
                "trees": {lbl: st.digest(t) for lbl, t in self.trees.items()}}


def public_view(task: dict) -> dict:
    """The task without grader keys. Refuses a nested grader key."""
    view = {k: v for k, v in task.items() if k not in GRADER_KEYS}
    for value in view.values():
        if isinstance(value, dict) and set(value) & set(GRADER_KEYS):
            raise ValueError("task carries a nested grader key; the loop must not see it")
    return view


def _edit(editor: Editor, ctx: EditContext, run: TaskRun) -> st.Tree:
    """One editor call with one retry; an invalid proposal inherits ctx.current."""
    err = ""
    for _attempt in range(2):
        run.budget["edits"] += 1
        try:
            prop = editor.propose(ctx)
            tree = st.validate(dict(prop.tree))
        except (st.TreeError, ValueError) as exc:
            err = str(exc)[:300]
            continue
        run.stages.append({"label": ctx.label, "dim": ctx.dim, "notes": prop.notes[:400],
                           "components": st.changed_components(ctx.current, tree),
                           "fell_back": False})
        return tree
    run.stages.append({"label": ctx.label, "dim": ctx.dim, "notes": "", "error": err,
                       "components": [], "fell_back": True})
    return dict(ctx.current)


def _roll(executor: Executor, task: dict, items: list[tuple[str, st.Tree]],
          run: TaskRun, workers: int) -> None:
    def one(item: tuple[str, st.Tree]) -> Rollout:
        label, tree = item
        try:
            return executor.execute(task, tree, label)
        except Exception as exc:  # a dead rollout is evidence, never a crash
            return Rollout(label, "", delivered=False, error=f"{type(exc).__name__}: {exc}")
    if workers > 1 and len(items) > 1:
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
            got = list(pool.map(one, items))
    else:
        got = [one(i) for i in items]
    for (label, tree), rollout in zip(items, got):
        run.trees[label] = tree
        run.rollouts[label] = rollout
        run.budget["rollouts"] += 1


def _pool(run: TaskRun, labels: list[str]) -> list[tuple[str, st.Tree, Rollout]]:
    return [(lbl, run.trees[lbl], run.rollouts[lbl]) for lbl in labels]


def _parallel(run, task, k, incumbent, executor, editor, lessons, workers):
    _roll(executor, task, [(f"base{i}", dict(incumbent)) for i in range(1, k + 1)], run, workers)
    ref = [run.rollouts[f"base{i}"] for i in range(1, k + 1)]
    probes = [(f"{d.lower()}{i}", d) for i in range(1, k + 1) for d in ("INV", "DOM")]
    trees = [(lbl, _edit(editor, EditContext(task, lbl, d, dict(incumbent), ref,
                                             lessons=lessons), run)) for lbl, d in probes]
    _roll(executor, task, trees, run, workers)
    pool = _pool(run, [lbl for lbl, _ in probes])
    aggs = [(f"agg{i}", _edit(editor, EditContext(task, f"agg{i}", "COMPOSE", dict(incumbent),
                                                  ref, pool, lessons), run))
            for i in range(1, k + 1)]
    _roll(executor, task, aggs, run, workers)
    run.finals = [lbl for lbl, _ in aggs]


def _sequential(run, task, k, incumbent, executor, editor, lessons, workers):
    _roll(executor, task, [(f"base{i}", dict(incumbent)) for i in range(1, k + 1)], run, workers)
    ref = [run.rollouts[f"base{i}"] for i in range(1, k + 1)]
    current, history = dict(incumbent), []
    for t in range(1, k + 1):
        probes = [(f"inv{t}", "INV"), (f"dom{t}", "DOM")]
        trees = [(lbl, _edit(editor, EditContext(task, lbl, d, dict(current), ref,
                                                 list(history), lessons), run))
                 for lbl, d in probes]
        _roll(executor, task, trees, run, workers)
        history += _pool(run, [lbl for lbl, _ in probes])
        comp = _edit(editor, EditContext(task, f"c{t}", "COMPOSE", dict(current), ref,
                                         list(history), lessons), run)
        _roll(executor, task, [(f"c{t}", comp)], run, workers)
        history += _pool(run, [f"c{t}"])
        current = comp
    run.finals = [f"c{t}" for t in range(1, k + 1)]


def run_task(task: dict, *, mode: str, k: int, incumbent: st.Tree, executor: Executor,
             editor: Editor, selector: Selector, lessons: list[dict] | None = None,
             workers: int = 1) -> TaskRun:
    """One Propose-Probe-Compose run on one task; returns the record and choice."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if int(k) < 1:
        raise ValueError("k must be at least 1")
    view = public_view(task)
    run = TaskRun(task_id=str(task.get("id", "")), mode=mode, k=int(k))
    step: Callable = _parallel if mode == "parallel" else _sequential
    step(run, view, int(k), st.validate(dict(incumbent)), executor, editor,
         list(lessons or []), workers)
    finals = {lbl: run.rollouts[lbl] for lbl in run.finals}
    run.chosen, run.why, run.scores = selector.choose(view, finals)
    if run.chosen not in finals:
        raise ValueError(f"selector chose {run.chosen!r}, not one of the finals")
    return run
