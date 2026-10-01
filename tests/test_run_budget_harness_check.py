"""The run's own check command is the harness's step, not the model's.

It is recorded in the budget record as a harness check and never charged to
the model's tool actions, so `max_tool_actions` set to 0 still lets the check
run. A check command the model runs itself, as a tool call, is the model's
action and is charged.
"""
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import canonicalize_operation
from harness.gateway_run_outcome import derive_run_outcome
from harness.plan_run_snapshot import thaw_json
from harness.run_budget import RunBudget, RunBudgetExceeded, harness_check
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_gateway_run_budget_signals import _drive, _op, _pytest
from tests.test_run_budget import Recorder, limits

PASSING = "def test_ok():\n    assert True\n"


def test_a_harness_check_is_recorded_and_not_charged():
    budget = RunBudget(limits(tool_actions=0))
    executor = budget.wrap_executor(Recorder(output="1 passed"), test_cmd="pytest -q")
    with harness_check(executor):
        assert executor.execute("run", {"cmd": "pytest -q"}).ok is True
    report = budget.report()
    assert report["used"]["tool_actions"] == 0 and report["harness_checks"] == 1
    # The model running the same command itself is its own action.
    with pytest.raises(RunBudgetExceeded) as stopped:
        executor.execute("run", {"cmd": "pytest -q"})
    assert stopped.value.limit == "tool_actions"


def _outcome(records, state):
    return derive_run_outcome(records, terminal_state=state)


def test_a_router_run_with_no_tool_actions_still_runs_its_check(tmp_path, monkeypatch):
    (tmp_path / "test_ok.py").write_text(PASSING, encoding="utf-8")
    op = _op(tmp_path, test_cmd=_pytest("test_ok.py"), run_budget={"max_tool_actions": 0})
    error, records, _ = _drive(tmp_path, monkeypatch, op, ["Nothing to change. Done."])
    assert error is None and records[-1]["kind"] == "result"
    report = records[-1]["payload"]["run_budget"]
    assert report["used"]["tool_actions"] == 0 and report["harness_checks"] == 1
    outcome = _outcome(records, "completed")
    assert outcome["budget"]["status"] == "within_limits"
    assert outcome["budget"]["harness_checks"] == 1
    assert outcome["completion"]["verdict"] == "verified"


def test_a_native_run_with_no_tool_actions_still_runs_its_check(tmp_path, monkeypatch):
    op = {"goal": "check it", "endpoint": "openai", "model": "gpt-6-astra",
          "root": str(tmp_path), "max_steps": 2, "max_tokens": 321, "timeout_s": 15,
          "allow_write": False, "allow_exec": True, "stream": True,
          "tool_protocol": "native", "test_cmd": "pytest -q",
          "run_budget": {"max_tool_actions": 0}, "data_refs": [], "credential_refs": []}
    ran = []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def __call__(self, method, url, headers, body, timeout):
            return 200, {"id": "resp_1", "model": "gpt-6-astra", "status": "completed",
                         "output": [{"type": "message", "role": "assistant", "content": [
                             {"type": "output_text", "text": "Done."}]}]}
    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    monkeypatch.setattr("harness.gateway_agent_native_tools.make_sandboxed_runner",
                        lambda **kw: lambda cmd, root: ran.append(cmd) or (True, "1 passed"))
    state = tmp_path.parent / (tmp_path.name + "_native_state")
    state.mkdir()
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), state))
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION, secrets=("sk-check-fixture-2b7",))
    run_private_agent(op, {"OPENAI_API_KEY": "sk-check-fixture-2b7"}, state, trace, None,
                      lambda e: None, binding=binding, deadline=time.monotonic() + 15)
    records = AgentTrace(state, OWNER, JOURNEY, OPERATION).read()
    report = records[-1]["payload"]["run_budget"]
    assert ran and report["used"]["tool_actions"] == 0 and report["harness_checks"] == 1
    assert _outcome(records, "completed")["budget"]["status"] == "within_limits"


def test_a_report_with_fewer_harness_checks_than_the_trace_is_unverifiable():
    budget = RunBudget(limits(tool_actions=5))
    check = {"kind": "tool_call", "content": "run " + json.dumps({"cmd": "pytest -q"}),
             "meta": {"gate": "test"}}
    records = [{"sequence": 0, "kind": "ledger", "record_sha256": "0" * 64, "payload": check},
               {"sequence": 1, "kind": "failure", "record_sha256": "0" * 64,
                "payload": {"run_budget": budget.report()}}]
    assert _outcome(records, "failed")["budget"]["reason"] == "BUDGET_UNDERCOUNTS_TRACE"
