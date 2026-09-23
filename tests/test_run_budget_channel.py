"""Limit errors are read from the provider and CLI channel, never from content.

A provider or a CLI reports a limit in its own fields: an HTTP or API status,
an error type, an error or result event, the CLI's own stderr and exit code.
Tool output and the model's answer are content the model produced or read,
and a limit named there is not a limit the run hit. These drive the real
parsers and paths; only the transport and the process are synthetic.
"""
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import _settle_budget, run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_cli_events import NativeEvents
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from harness.run_budget import RunBudget, resolve_limits
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_gateway_run_budget import _cli
from tests.test_gateway_run_budget_signals import _assistant, _result

FIXTURE_429 = 'mock.return_value = {"status": 429, "error": "slow down"}'
FIXTURE_TYPE = 'RATE = {"type": "rate_limit_error", "message": "retry"}'
#: The assistant event claude 2.1.251 streamed for a real billing error.
BILLING = {"type": "assistant", "error": "billing_error", "is_api_error_message": True,
           "message": {"id": "17f33386", "model": "<synthetic>", "role": "assistant",
                       "content": [{"type": "text", "text": "Credit balance is too low"}]}}


def _budget():
    return RunBudget(resolve_limits({"max_steps": 6}))


def _claude(budget, rows, tools=("Read", "Bash")):
    parser = NativeEvents("claude-cli", list(tools), lambda e: None, max_steps=6,
                          budget=budget)
    for row in rows:
        parser.feed(json.dumps(row))
    return parser


def _bash(i, printed):
    return [{"type": "assistant", "message": {"id": f"m{i}", "content": [
                {"type": "tool_use", "id": f"t{i}", "name": "Bash",
                 "input": {"command": "cat fixture"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"t{i}", "content": printed,
                 "is_error": False}]}}]


def test_cli_tool_output_that_prints_limit_fixtures_does_not_stop_the_session():
    budget = _budget()
    rows = _bash(1, FIXTURE_429) + _bash(2, FIXTURE_TYPE) + _bash(3, "ok")
    _claude(budget, rows + [_result(num_turns=3)])
    report = budget.report()
    assert report["limit_signal_steps"] == [] and report["false_success_count"] == 0
    _settle_budget({"final": "done"}, budget)


def test_codex_command_output_is_not_read_for_limits():
    budget = _budget()
    parser = NativeEvents("codex-cli", ["command_execution"], lambda e: None,
                          max_steps=6, budget=budget)
    for i, printed in enumerate((FIXTURE_429, FIXTURE_TYPE, FIXTURE_429)):
        parser.feed(json.dumps({"type": "item.completed", "item": {
            "id": f"c{i}", "type": "command_execution", "command": "cat",
            "aggregated_output": printed, "exit_code": 0}}))
    assert budget.report()["limit_signal_steps"] == []


@pytest.mark.parametrize("final", [
    "Rate limited requests now back off with jitter.",
    "HTTP 429 responses are now retried with backoff.",
    "Claude AI usage limit reached|1760000000"])
def test_a_short_cli_answer_completes_on_the_cli_path(final, tmp_path, monkeypatch):
    # Through _run_checked with a native_cli_session binding, so the test fails
    # if the answer check comes back on the CLI path only.
    from types import SimpleNamespace
    from harness.gateway_agent_execution import _run_checked
    monkeypatch.setattr("harness.gateway_cli_execution.run_cli_session",
                        lambda *args, **kwargs: {"final": final})
    budget, completion = _budget(), {}
    result = _run_checked(tmp_path, None, {"execution_mode": "native_cli_session"}, {},
                          SimpleNamespace(entries=[]), SimpleNamespace(root=None, identity=None),
                          time.monotonic() + 60, lambda e: None, {"goal": "g"}, budget, [],
                          completion)
    assert result["final"] == final
    assert budget.report()["false_success_count"] == 0


def test_a_cli_api_error_event_is_recorded_with_its_error_type(tmp_path, monkeypatch):
    budget = _budget()
    rows = [BILLING, _result(is_error=True, api_error_status=400, total_cost_usd=0,
                             result="Credit balance is too low")]
    with pytest.raises(GatewayOperationError) as failed:
        _cli(tmp_path, monkeypatch, rows, budget, returncode=1)
    assert failed.value.code == "AGENT_CLI_INCOMPLETE"
    steps = budget.report()["limit_signal_steps"]
    assert [(s["tool"], s["signal"], s["match"]) for s in steps] == [
        ("cli_api_error", "billing", "billing_error")]


def test_a_success_result_after_a_limit_event_is_a_false_success(tmp_path, monkeypatch):
    budget = _budget()
    limited = {**BILLING, "error": "rate_limit"}
    result, _ = _cli(tmp_path, monkeypatch, [limited, _result()], budget)
    with pytest.raises(GatewayOperationError) as failed:
        _settle_budget(result, budget)
    assert failed.value.code == "AGENT_FALSE_SUCCESS"
    assert budget.report()["false_success_steps"][0]["match"] == "rate_limit"


def test_the_clis_own_stderr_on_exit_zero_is_read(tmp_path, monkeypatch):
    budget = _budget()
    result, _ = _cli(tmp_path, monkeypatch, [_assistant("m1"), _result()], budget,
                     stderr="Claude AI usage limit reached|1760000000\n")
    with pytest.raises(GatewayOperationError) as failed:
        _settle_budget(result, budget)
    assert failed.value.code == "AGENT_FALSE_SUCCESS"
    step = budget.report()["limit_signal_steps"][0]
    assert (step["tool"], step["match"]) == ("cli_stderr", "usage limit reached")


def _router(tmp_path, monkeypatch, replies, *, exec_output="ok"):
    """The real router path; each reply is (status, body) or answer text."""
    def factory(**authority):
        sent = []

        def transport(method, url, headers, body, timeout):
            reply = replies[min(len(sent), len(replies) - 1)]
            sent.append(reply)
            if type(reply) is tuple:
                return reply
            return 200, {"model": authority["model"],
                         "choices": [{"message": {"content": reply}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    monkeypatch.setattr("harness.router_agent.make_sandboxed_runner",
                        lambda **kw: lambda cmd, root: (True, exec_output))
    op = {"goal": "list", "endpoint": "ollama", "model": "qwen2.5-coder:14b",
          "root": str(tmp_path), "max_steps": 6, "allow_write": False, "allow_exec": True,
          "stream": True, "data_refs": [], "credential_refs": []}
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    try:
        run_private_agent(op, {}, tmp_path, trace, None, lambda e: None,
                          binding=binding, deadline=time.monotonic() + 60)
        error = None
    except Exception as exc:  # the worker maps any raise to a fixed reason
        error = exc
    return error, AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()[-1]["payload"]


def test_router_tool_output_quoting_a_limit_does_not_trip(tmp_path, monkeypatch):
    run = 'TOOL run {"cmd": "cat fixture.json"}'
    error, payload = _router(tmp_path, monkeypatch, [run, run, run, "Read the fixture."],
                             exec_output=FIXTURE_429)
    assert error is None
    report = payload["run_budget"]
    assert report["limit_signal_steps"] == [] and report["false_success_count"] == 0


def test_a_provider_429_is_recorded_from_its_status_and_error_type(tmp_path, monkeypatch):
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    error, payload = _router(tmp_path, monkeypatch, [(429, body)])
    from harness.gateway_agent_failures import failure_reason
    assert error is not None and failure_reason(error) == "EXTERNAL_ACTION_FAILED"
    steps = payload["run_budget"]["limit_signal_steps"]
    assert [(s["tool"], s["signal"], s["match"]) for s in steps] == [
        ("provider", "rate_limit", "rate_limit_error")]
    assert payload["run_budget"]["false_success_count"] == 0
