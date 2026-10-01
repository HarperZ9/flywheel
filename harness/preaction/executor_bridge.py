"""executor_bridge.py -- wire the pre-action monitor into ToolExecutor.execute.

Kept out of local_tools.py so that module does not grow past its file-gate
count. The monitor is on by default: when the executor was built with no
monitor, the first gated call builds the default one, so no call path skips
assessment. The executor's own ToolGate becomes layer 0, so a gate refusal is
recorded as a pre-action BLOCK and keeps its exact "[gate] ..." text.
"""
from __future__ import annotations

import os
from pathlib import Path

from .contract import ProposedCall, RunContext


def ensure_monitor(executor):
    if executor.monitor is False:
        return None
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
    monitor = ensure_monitor(executor)
    if monitor is None:
        return None
    monitor.layer0 = lambda c, _ctx: executor.gate.check(c.tool, c.args)
    gate = monitor.gate(_call(executor, name, args), _ctx(executor))
    gate.result_text = _result_text(gate)
    return gate


def _result_text(gate) -> str:
    layer0 = next((r for r in gate.assessment.reasons if r.get("id") == "layer0/gate"), None)
    return f"[gate] {layer0['reason']}" if layer0 else gate.agent_text


def preaction_observe(executor, name: str, args: dict, gate, result) -> None:
    try:
        executor.monitor.observe(_call(executor, name, args), _ctx(executor), gate, result.output)
    except Exception:  # noqa: BLE001 -- observation must never break the call path
        pass
