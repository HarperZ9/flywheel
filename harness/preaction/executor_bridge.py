"""executor_bridge.py -- wire the pre-action monitor into ToolExecutor.execute.

Kept out of local_tools.py so that module does not grow past its file-gate
count. The monitor is on by default: when the executor was built with no
monitor, the first gated call builds the default one, so no call path skips
assessment. The executor's own ToolGate becomes layer 0, so a gate refusal is
recorded as a pre-action BLOCK and keeps its exact "[gate] ..." text.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from .contract import BLOCK, UNVERIFIABLE, Assessment, ProposedCall, RunContext

_log = logging.getLogger(__name__)


class _FailClosed:
    """The gate result when the monitor itself cannot answer: the call does not run."""

    def __init__(self, path_id: str, why: str) -> None:
        self.verdict, self.run = BLOCK, False
        self.assessment = Assessment(verdict=BLOCK, path_id=path_id, coverage=UNVERIFIABLE,
                                     reasons=[{"layer": 0, "id": "monitor_error", "family": "monitor",
                                               "action": BLOCK, "reason": why}])
        self.result_text = f"held: {why}; failing closed"


def ensure_monitor(executor):
    if executor.monitor is False:
        # The only off switch is offswitch.monitor_off with a consumed owner
        # grant, which records every call UNVERIFIABLE. A constructor flag that
        # silently skipped assessment would be an unrecorded bypass.
        raise ValueError("monitor=False is not an off switch; use preaction.offswitch.monitor_off")
    if executor.monitor is None and not executor._monitor_built:
        from .core import Monitor
        executor.monitor = Monitor(home=Path(executor.root) / ".flywheel-preaction")
        executor._monitor_built = True
    return executor.monitor or None


def _call(executor, name, args):
    path_id = "E6" if name in executor.external else "E1"
    return ProposedCall(tool=name, args=args, harness="flywheel", path_id=path_id,
                        tool_use_id=f"{executor._receipt_run_id}:{executor._receipt_seq + 1}")


def _ctx(executor):
    return RunContext(run_id=executor._receipt_run_id or "default",
                      workspace=os.path.realpath(executor.root))


def preaction_gate(executor, name: str, args: dict):
    """Assess one call. Any failure inside the monitor returns a gate that does
    not run the call; it never raises into the loop and never passes."""
    path_id = "E6" if name in getattr(executor, "external", {}) else "E1"
    try:
        monitor = ensure_monitor(executor)
        if monitor is None:
            return _FailClosed(path_id, "no monitor")
        monitor.layer0 = lambda c, _ctx: executor.gate.check(c.tool, c.args)
        gate = monitor.gate(_call(executor, name, args), _ctx(executor))
        gate.result_text = _result_text(gate)
        return gate
    except Exception as exc:  # noqa: BLE001 -- logged, then the call does not run
        _log.error("pre-action monitor failed on %s: %s: %s", name, type(exc).__name__, exc)
        return _FailClosed(path_id, f"monitor error ({type(exc).__name__})")


def _result_text(gate) -> str:
    layer0 = next((r for r in gate.assessment.reasons if r.get("id") == "layer0/gate"), None)
    return f"[gate] {layer0['reason']}" if layer0 else gate.agent_text


def preaction_observe(executor, name: str, args: dict, gate, result) -> None:
    try:
        executor.monitor.observe(_call(executor, name, args), _ctx(executor), gate, result.output)
    except Exception as exc:  # noqa: BLE001 -- the call already ran; log the lost taint input
        _log.warning("pre-action observe failed on %s: %s: %s; taint not updated",
                     name, type(exc).__name__, exc)
