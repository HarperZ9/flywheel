"""A budget stop must retain files changed through commands in completion."""
import json
import sys
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.gateway_run_outcome import derive_run_outcome
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_gateway_run_budget_signals import _drive, _op


def _command(root):
    (root / "writer.py").write_text(
        "from pathlib import Path\n"
        "Path('deliverable.txt').write_text('work', encoding='utf-8')\n",
        encoding="utf-8")
    return f'"{sys.executable}" writer.py'


def _assert_completion(root, records):
    assert (root / "deliverable.txt").read_text(encoding="utf-8") == "work"
    failures = [r for r in records if r["kind"] == "failure"]
    assert len(failures) == 1 and records[-1] is failures[0]
    payload = failures[0]["payload"]
    assert payload["message"] == "AGENT_RUN_BUDGET_EXHAUSTED"
    report = payload["completion"]
    files = [i for i in report["items"] if i["kind"] == "file"]
    assert [(i["path"], i["status"], i["detail"]) for i in files] == [
        ("deliverable.txt", "claimed", "changed_by_command")]
    assert report["items"][-1]["detail"] == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert report["counts"] == {"verified": 0, "claimed": 1, "failed": 1}
    outcome = derive_run_outcome(records, terminal_state="failed")
    assert outcome["completion"]["status"] == "recorded"
    assert outcome["budget"]["tripped"] == "model_calls"


def test_router_command_write_is_listed_after_budget_stop(tmp_path, monkeypatch):
    cmd = _command(tmp_path)
    op = _op(tmp_path, run_budget={"max_model_calls": 1})
    error, records, prompts = _drive(tmp_path, monkeypatch, op,
                                    ['TOOL run ' + json.dumps({"cmd": cmd}), "Done."])
    assert error.code == "AGENT_RUN_BUDGET_EXHAUSTED" and len(prompts) == 1
    _assert_completion(tmp_path, records)


def _native_run(tmp_path, monkeypatch):
    cmd = _command(tmp_path)
    sent = []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def __call__(self, method, url, headers, body, timeout):
            sent.append(json.loads(body))
            return 200, {"id": "resp_1", "model": "gpt-6-astra",
                         "status": "completed", "usage": {"total_tokens": 9},
                         "output": [{"type": "function_call", "id": "fc_1",
                                     "call_id": "call_1", "name": "run",
                                     "arguments": json.dumps({"cmd": cmd})}]}

    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    monkeypatch.setattr("harness.gateway_agent_native_tools.make_sandboxed_runner",
                        lambda **kw: None)
    state = tmp_path.parent / (tmp_path.name + "_state")
    state.mkdir()
    op = _op(tmp_path, endpoint="openai", model="gpt-6-astra", tool_protocol="native",
             run_budget={"max_model_calls": 1})
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), state))
    secret = "sk-budget-fixture-9f3"
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION, secrets=(secret,))
    with pytest.raises(GatewayOperationError) as stopped:
        run_private_agent(op, {"OPENAI_API_KEY": secret}, state, trace, None,
                          lambda e: None, binding=binding, deadline=time.monotonic() + 30)
    assert stopped.value.code == "AGENT_RUN_BUDGET_EXHAUSTED" and len(sent) == 1
    records = AgentTrace(state, OWNER, JOURNEY, OPERATION).read()
    return stopped.value, records


def test_native_command_write_is_listed_after_budget_stop(tmp_path, monkeypatch):
    _, records = _native_run(tmp_path, monkeypatch)
    _assert_completion(tmp_path, records)


@pytest.mark.parametrize("path", ["router", "native"])
def test_failure_snapshot_error_preserves_stop_and_marks_completion_unavailable(
        tmp_path, monkeypatch, path):
    def unavailable(*args, **kwargs):
        raise OSError("private-snapshot-diagnostic")

    monkeypatch.setattr("harness.router_agent._workspace_post", unavailable)
    if path == "native":
        error, records = _native_run(tmp_path, monkeypatch)
    else:
        cmd = _command(tmp_path)
        error, records, _ = _drive(tmp_path, monkeypatch,
            _op(tmp_path, run_budget={"max_model_calls": 1}),
            ['TOOL run ' + json.dumps({"cmd": cmd})])
    assert error.code == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert (tmp_path / "deliverable.txt").exists()
    failures = [r for r in records if r["kind"] == "failure"]
    assert len(failures) == 1
    report = failures[0]["payload"]["completion"]
    assert report["verdict"] == "unavailable"
    assert report["reason"] == "WORKSPACE_CAPTURE_FAILED:OSError"
    assert "private-snapshot-diagnostic" not in json.dumps(records)
    outcome = derive_run_outcome(records, terminal_state="failed")
    assert outcome["completion"]["status"] == "unverifiable"
    assert outcome["budget"]["tripped"] == "model_calls"
