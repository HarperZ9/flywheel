"""A run the aggregate deadline stops mid-step still gets a budget record.

The deadline stops the worker's process tree wherever it is, so the worker
writes no failure record. The gateway then writes one from what the private
trace shows, with the wall-time stop, so the card can say the run was stopped
by its time limit and what it spent up to then.
"""
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import canonicalize_operation
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_run_outcome import derive_run_outcome
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started
from tests.test_gateway_run_budget import _operation


class _TreeStopped(BaseException):
    """Stands in for the process tree being stopped in the middle of a step."""


def _stopped_mid_step(tmp_path, monkeypatch):
    """A real router run that is cut off during its second model call."""
    calls = []

    def factory(**authority):
        def transport(method, url, headers, body, timeout):
            calls.append(1)
            if len(calls) > 1:
                raise _TreeStopped()
            return 200, {"model": authority["model"], "usage": {"total_tokens": 40},
                         "choices": [{"message": {"content": 'TOOL list_dir {"path": "."}'}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    op = _operation(tmp_path, timeout_s=30)
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    with pytest.raises(_TreeStopped):
        run_private_agent(op, {}, tmp_path, trace, None, lambda e: None,
                          binding=binding, deadline=time.monotonic() + 60)


def test_a_deadline_stop_mid_step_writes_a_wall_time_budget_record(tmp_path, monkeypatch):
    _started(tmp_path, _queued(tmp_path))
    _stopped_mid_step(tmp_path, monkeypatch)
    assert AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()[-1]["kind"] == "ledger"
    service = _service(tmp_path)
    service._terminal(OWNER, OPERATION, WorkerOutcome(
        "failed", {"reason": "OPERATION_DEADLINE_EXCEEDED"}))
    result = service.result(OWNER, OPERATION)["result"]
    assert result["reason"] == "OPERATION_DEADLINE_EXCEEDED"
    budget = result["run_outcome"]["budget"]
    assert (budget["status"], budget["tripped"]) == ("stopped", "wall_time")
    assert budget["used"]["model_calls"] == 2 and budget["used"]["tool_actions"] == 1
    assert budget["used"]["usage_tokens"] == 40
    assert budget["reporting"] == {"calls_with_tokens": 1, "calls_without_tokens": 1,
                                   "calls_with_cost": 0}
    assert budget["limits"]["wall_time_ms"] == budget["used"]["wall_time_ms"] == 30_000
    records = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()
    assert records[-1]["kind"] == "failure"
    assert records[-1]["payload"]["recorded_by"] == "gateway_deadline"


def test_a_worker_record_is_never_overwritten_and_other_stops_add_none(tmp_path, monkeypatch):
    from harness.gateway_agent_execution import recovered_projection
    _stopped_mid_step(tmp_path, monkeypatch)
    count = len(AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read())
    recovered_projection(tmp_path, OWNER, JOURNEY, OPERATION, "failed", "OPERATION_INTERRUPTED")
    assert len(AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()) == count
    for _ in range(2):
        recovered_projection(tmp_path, OWNER, JOURNEY, OPERATION, "failed",
                             "OPERATION_DEADLINE_EXCEEDED")
    records = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()
    assert len(records) == count + 1
    derived = derive_run_outcome(records, terminal_state="failed")["budget"]
    assert derived["tripped"] == "wall_time"
    assert json.dumps(records[-1]["payload"]).count("run_budget") == 1
