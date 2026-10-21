"""self_improve_stream.py -- harnessing-level recursion across a task stream.

Each task runs the grader-free Propose-Probe-Compose loop from the current
incumbent harness and the admitted lessons. The chosen final serves that task.
Then the chosen harness goes to the held-out gate, and only what passes there
becomes the next incumbent and an admitted lesson, with a receipt.

So a task always gets the loop's best contrast-chosen answer, while the state
every later task inherits moves only on graded, held-out evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import self_improve_tree as st
from .self_improve_gate import ADOPT, HeldOutGate
from .self_improve_library import LessonLibrary
from .self_improve_loop import Editor, Executor, Selector, TaskRun, run_task
from .self_improve_receipt import build_edit_receipt

Reflect = Callable[[TaskRun, list[str]], tuple[str, str]]


def default_reflect(run: TaskRun, components: list[str]) -> tuple[str, str]:
    """A plain lesson: which components changed and that they passed the gate."""
    cue = f"tasks like {run.task_id}"
    return cue, f"edits to {', '.join(components)} passed the held-out gate"


@dataclass
class StreamConfig:
    mode: str = "parallel"
    k: int = 1
    workers: int = 1
    gate_enabled: bool = True     # False reproduces ungated carry-over, for ablation


@dataclass
class Stream:
    executor: Executor
    editor: Editor
    selector: Selector
    gate: HeldOutGate
    base: st.Tree
    config: StreamConfig = field(default_factory=StreamConfig)
    reflect: Reflect = default_reflect
    library: LessonLibrary = field(default_factory=LessonLibrary)
    receipts: list[dict] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    last_run: TaskRun | None = None

    def __post_init__(self) -> None:
        if not self.library.versions:
            self.library.commit_version(self.base, receipt_seal="base")

    def step(self, task: dict) -> dict:
        """Run one task; return the delivered rollout and the gate decision."""
        incumbent = self.library.incumbent()
        served = self.library.served()
        run = run_task(task, mode=self.config.mode, k=self.config.k, incumbent=incumbent,
                       executor=self.executor, editor=self.editor, selector=self.selector,
                       lessons=served, workers=self.config.workers)
        self.last_run = run
        candidate = run.chosen_tree()
        if self.config.gate_enabled:
            gate = self.gate.review(incumbent, candidate)
        else:
            gate = _ungated(incumbent, candidate)
        receipt = build_edit_receipt(parent=incumbent, candidate=candidate, run=run,
                                     gate=gate, provenance={"task_id": run.task_id})
        self.receipts.append(receipt)
        lesson_id = ""
        if gate["decision"] == ADOPT:
            lesson_id = self._learn(run, gate, receipt, [s["id"] for s in served])
        row = {"task_id": run.task_id, "chosen": run.chosen,
               "output": run.rollouts[run.chosen].output, "decision": gate["decision"],
               "adopted_components": gate["adopted_components"], "lesson_id": lesson_id,
               "incumbent_digest": st.digest(incumbent), "budget": dict(run.budget),
               "gate_executions": gate.get("gate_executions", 0),
               "receipt_seal": receipt["seal_sha256"]}
        self.rows.append(row)
        return row

    def _learn(self, run: TaskRun, gate: dict, receipt: dict, parents: list[str]) -> str:
        cue, text = self.reflect(run, gate["adopted_components"])
        lid = self.library.add(cue=cue, lesson=text, components=gate["adopted_components"],
                               source_task=run.task_id, receipt_seal=receipt["seal_sha256"],
                               parents=parents)
        if self.config.gate_enabled and not self.library.admit(lid, receipt):
            return lid
        if not self.config.gate_enabled:
            self.library._log("admit", lesson_id=lid, reason="ungated ablation")
        self.library.commit_version(gate["tree"], receipt_seal=receipt["seal_sha256"],
                                    lessons=[lid])
        return lid

    def run(self, tasks: list[dict]) -> list[dict]:
        return [self.step(t) for t in tasks]


def _ungated(incumbent: st.Tree, candidate: st.Tree) -> dict:
    """The ablation arm: adopt whatever the contrast chose, with no held-out check.

    Its receipts verify as INCONSISTENT by design, because nothing supports the
    decision they record.
    """
    comps = st.changed_components(incumbent, candidate)
    decision = ADOPT if comps else "REJECT"
    return {"decision": decision, "reason": "ungated ablation: contrast choice adopted",
            "adopted_components": comps, "tree": candidate if comps else incumbent,
            "heldout": None, "attribution": [], "gate_executions": 0,
            "policy": {}, "does_not_prove": ["nothing: no held-out evidence was taken"]}
