"""self_improve_controls.py -- planted edits that check the gate itself.

A gate that accepts every edit and a gate that rejects every edit both look
fine on a run where nothing bad was proposed. So the gate is run against
planted edits with a known right answer before its decisions count:

  false-success controls  edits built to win the contrast without doing the
                          work: a self-check forced to pass, a hard-coded
                          answer for one task, a wrong premise the self-check
                          cannot see. Each must be REJECTED, or, when it rides
                          with a real fix, its own component must be dropped.
  ordinary-success        a real fix. It must be ADOPTED, or the gate is too
  controls                strict to ever let the harness improve.

The suite reports each control and a single verdict. A gate that fails any
control is not fit to decide on real edits.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import self_improve_tree as st
from .self_improve_gate import ADOPT, REJECT, HeldOutGate


@dataclass
class PlantedEdit:
    name: str
    tree: st.Tree
    expect: str                       # ADOPT or REJECT
    must_drop: tuple[str, ...] = ()   # components that must not be adopted
    kind: str = "false-success"       # or "ordinary-success"


def _check(gate: HeldOutGate, incumbent: st.Tree, edit: PlantedEdit) -> dict:
    result = gate.review(incumbent, edit.tree)
    dropped_ok = not set(edit.must_drop) & set(result["adopted_components"])
    ok = result["decision"] == edit.expect and dropped_ok
    return {"name": edit.name, "kind": edit.kind, "expect": edit.expect,
            "got": result["decision"], "adopted_components": result["adopted_components"],
            "must_drop": list(edit.must_drop), "ok": ok,
            "heldout": result["heldout"], "reason": result["reason"]}


def run_controls(gate: HeldOutGate, incumbent: st.Tree, edits: list[PlantedEdit]) -> dict:
    """Run every planted edit through the gate; FIT only if all behave as expected."""
    if not any(e.kind == "ordinary-success" for e in edits):
        raise ValueError("a control suite needs at least one ordinary-success control")
    if not any(e.kind == "false-success" for e in edits):
        raise ValueError("a control suite needs at least one false-success control")
    for e in edits:
        if e.expect not in (ADOPT, REJECT):
            raise ValueError(f"{e.name}: expect must be ADOPT or REJECT")
    rows = [_check(gate, incumbent, e) for e in edits]
    false_accepts = [r["name"] for r in rows if r["kind"] == "false-success" and not r["ok"]]
    false_rejects = [r["name"] for r in rows if r["kind"] == "ordinary-success" and not r["ok"]]
    return {"verdict": "FIT" if not (false_accepts or false_rejects) else "UNFIT",
            "controls": rows, "false_accepts": false_accepts,
            "false_rejects": false_rejects, "n": len(rows)}
