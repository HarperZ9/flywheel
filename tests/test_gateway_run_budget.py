"""The breaker stops real bound runs and the projection says why."""
import copy
import json
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import _settle_budget, run_private_agent
from harness.gateway_agent_failures import failure_reason
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.gateway_operation_process import WorkerOutcome
from harness.gateway_run_outcome import derive_run_outcome, validate_run_outcome
from harness.plan_run_snapshot import thaw_json
from harness.run_budget import RunBudget, RunBudgetExceeded, resolve_limits
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started

LIMIT_TEXT = "Claude AI usage limit reached|1760000000"


def _operation(tmp_path, **extra):
    return {"goal": "list the workspace", "endpoint": "ollama",
            "model": "qwen2.5-coder:14b", "root": str(tmp_path), "max_steps": 6,
            "allow_write": False, "allow_exec": False, "stream": True,
            "data_refs": [], "credential_refs": [], **extra}


def _run(tmp_path, monkeypatch, operation, replies, usage=None):
    """Drive the real router path; only the provider transport is synthetic."""
    sent = []

    def factory(**authority):
        def transport(method, url, headers, body, timeout):
            text = replies[min(len(sent), len(replies) - 1)]
            sent.append(text)
            reply = {"model": authority["model"], "choices": [{"message": {"content": text}}]}
            if usage is not None:
                reply["usage"] = usage
            return 200, reply
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    binding = thaw_json(freeze_agent_binding(
        canonicalize_operation("agent.run", operation), tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    try:
        projection = run_private_agent(operation, {}, tmp_path, trace, None, lambda e: None,
                                       binding=binding, deadline=time.monotonic() + 60)
        error = None
    except GatewayOperationError as exc:
        projection, error = None, exc
    return projection, error, AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read(), sent


def _ledger_kinds(records, kind):
    return sum(1 for r in records if r["kind"] == "ledger" and r["payload"]["kind"] == kind)


def test_tool_action_limit_stops_a_bound_run_before_the_next_action(tmp_path, monkeypatch):
    op = _operation(tmp_path, run_budget={"max_tool_actions": 2})
    _, error, records, _ = _run(tmp_path, monkeypatch, op, ['TOOL list_dir {"path": "."}'])
    assert error is not None and error.code == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert failure_reason(error) == "AGENT_RUN_BUDGET_EXHAUSTED"
    report = records[-1]["payload"]["run_budget"]
    assert records[-1]["kind"] == "failure"
    assert report["tripped"] == "tool_actions" and report["used"]["tool_actions"] == 2
    assert _ledger_kinds(records, "tool_call") == 2
    outcome = derive_run_outcome(records, terminal_state="failed")["budget"]
    assert outcome["status"] == "stopped" and outcome["tripped"] == "tool_actions"


def test_reported_tokens_past_the_limit_stop_the_next_step(tmp_path, monkeypatch):
    op = _operation(tmp_path, run_budget={"max_usage_tokens": 1_000})
    _, error, records, sent = _run(tmp_path, monkeypatch, op, ['TOOL list_dir {"path": "."}'],
                                   usage={"prompt_tokens": 1_200, "completion_tokens": 20})
    assert error.code == "AGENT_RUN_BUDGET_EXHAUSTED" and len(sent) == 1
    report = records[-1]["payload"]["run_budget"]
    assert report["tripped"] == "usage_tokens" and report["used"]["usage_tokens"] == 1_220
    assert _ledger_kinds(records, "tool_call") == 0


def test_a_router_final_answer_is_model_prose_and_is_not_read_for_a_limit(
        tmp_path, monkeypatch):
    # A provider limit on this path fails the call as a non-2xx response. The
    # answer text is the model's own, so quoting a limit does not fail the run.
    projection, error, records, _ = _run(tmp_path, monkeypatch, _operation(tmp_path),
                                         [LIMIT_TEXT])
    assert error is None and projection["state"] == "completed"
    assert records[-1]["payload"]["run_budget"]["false_success_count"] == 0


def test_an_ordinary_run_completes_and_records_what_it_spent(tmp_path, monkeypatch):
    projection, error, records, _ = _run(
        tmp_path, monkeypatch, _operation(tmp_path), ["Three files."],
        usage={"total_tokens": 40})
    assert error is None and projection["state"] == "completed"
    report = records[-1]["payload"]["run_budget"]
    assert report["status"] == "within_limits"
    assert report["used"]["model_calls"] == 1 and report["used"]["usage_tokens"] == 40
    assert report["limits"] == resolve_limits(_operation(tmp_path))
    assert derive_run_outcome(records, terminal_state="completed")["budget"]["status"] \
        == "within_limits"


def test_the_terminal_projection_carries_the_outcome_and_rejects_a_forged_one(
        tmp_path, monkeypatch):
    _started(tmp_path, _queued(tmp_path))
    op = _operation(tmp_path, run_budget={"max_tool_actions": 1})
    _, error, _, _ = _run(tmp_path, monkeypatch, op, ['TOOL list_dir {"path": "."}'])
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    trace.read()
    service = _service(tmp_path)
    service._terminal(OWNER, OPERATION, WorkerOutcome(
        "failed", trace.projection("failed", reason=failure_reason(error))))
    result = service.result(OWNER, OPERATION)["result"]
    assert result["reason"] == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert result["run_outcome"]["budget"]["tripped"] == "tool_actions"
    forged = copy.deepcopy(result["run_outcome"])
    forged["budget"]["status"] = "within_limits"
    with pytest.raises(ValueError):
        validate_run_outcome(trace.read(), terminal_state="failed", submitted=forged)


def test_native_provider_requests_are_charged_to_the_budget(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("readback", encoding="utf-8")
    op = _operation(tmp_path, endpoint="openai", model="gpt-6-astra",
                    tool_protocol="native", run_budget={"max_model_calls": 1})
    sent = []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def __call__(self, method, url, headers, body, timeout):
            sent.append(json.loads(body))
            return 200, {"id": f"resp_{len(sent)}", "model": "gpt-6-astra",
                         "status": "completed", "usage": {"total_tokens": 9},
                         "output": [{"type": "function_call", "id": f"fc_{len(sent)}",
                                     "call_id": f"call_{len(sent)}", "name": "read_file",
                                     "arguments": json.dumps({"path": "fixture.txt"})}]}
    monkeypatch.setattr("harness.gateway_agent_native_tools.BoundAgentTransport", Transport)
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION, secrets=("sk-budget-fixture-9f3",))
    with pytest.raises(GatewayOperationError) as stopped:
        run_private_agent(op, {"OPENAI_API_KEY": "sk-budget-fixture-9f3"}, tmp_path, trace, None,
                          lambda e: None, binding=binding, deadline=time.monotonic() + 15)
    assert stopped.value.code == "AGENT_RUN_BUDGET_EXHAUSTED" and len(sent) == 1
    records = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()
    report = records[-1]["payload"]["run_budget"]
    assert report["tripped"] == "model_calls" and report["used"]["usage_tokens"] == 9
    assert derive_run_outcome(records, terminal_state="failed")["budget"]["status"] == "stopped"


def _records_with(report, *, tool_calls=0):
    rows = [{"sequence": i, "kind": "ledger", "record_sha256": "0" * 64,
             "payload": {"kind": "tool_call", "content": "list_dir {}"}}
            for i in range(tool_calls)]
    rows.append({"sequence": tool_calls, "kind": "failure", "record_sha256": "0" * 64,
                 "payload": {"error_type": "RunBudgetExceeded", "run_budget": report}})
    return rows


def _stopped_report(used_tools):
    budget = RunBudget({"model_calls": 3, "tool_actions": 2, "usage_tokens": 1000,
                        "cost_micros": 1000, "limit_signals": 2, "wall_time_ms": 1000})
    budget.used["tool_actions"] = used_tools
    budget.tripped = "tool_actions"
    return budget.report()


def test_a_stop_the_numbers_do_not_support_is_unverifiable():
    derived = derive_run_outcome(_records_with(_stopped_report(1)), terminal_state="failed")
    assert derived["budget"]["status"] == "unverifiable"
    assert derived["budget"]["reason"] == "BUDGET_STOP_NOT_SUPPORTED"


def test_a_report_that_undercounts_the_trace_is_unverifiable():
    derived = derive_run_outcome(_records_with(_stopped_report(2), tool_calls=3),
                                 terminal_state="failed")
    assert derived["budget"]["reason"] == "BUDGET_UNDERCOUNTS_TRACE"


class _Process:
    def __init__(self, rows, stderr="", returncode=0):
        self.rows, self.closed = rows, False
        self.stderr, self.returncode = stderr, returncode

    def resume(self):
        return True

    def stdout_snapshot(self):
        return ("\n".join(json.dumps(r) for r in self.rows) + "\n").encode(), False

    def capture_overflow(self):
        return False

    def wait(self, timeout_s):
        from types import SimpleNamespace
        return SimpleNamespace(returncode=self.returncode, malformed_output=False,
                               timed_out=False, stdout=self.stdout_snapshot()[0].decode(),
                               stderr=self.stderr, elapsed_ms=1)

    def close(self):
        self.closed = True


def _cli(tmp_path, monkeypatch, rows, budget, **process):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    monkeypatch.setattr(execution, "verify_runtime", lambda r: None)
    monkeypatch.setattr(execution, "pin_runtime",
                        lambda r: __import__("contextlib").nullcontext())
    monkeypatch.setattr(execution, "check_configuration_boundary", lambda *a: None)
    binding = {"endpoint": {"name": "claude-cli"}, "model": {"model_id": "exact"},
               "budget": {"max_steps": 3},
               "cli_session": session_profile("claude-cli", allow_write=False, allow_exec=False),
               "cli_runtime": {"executable": "fixture.exe", "auth_directory": str(tmp_path)}}
    proc = _Process(rows, **process)
    result = execution.run_cli_session("read", binding, tmp_path, time.monotonic() + 5,
                                       lambda e: None, launcher=lambda *a, **k: proc,
                                       budget=budget)
    return result, proc


def test_cli_exit_zero_success_after_a_limit_event_is_failed(tmp_path, monkeypatch):
    budget = RunBudget(resolve_limits({"max_steps": 3}))
    limited = {"type": "assistant", "error": "rate_limit", "is_api_error_message": True,
               "message": {"id": "m1", "model": "<synthetic>",
                           "content": [{"type": "text", "text": LIMIT_TEXT}]}}
    rows = [limited, {"type": "result", "is_error": False, "subtype": "success",
                      "result": LIMIT_TEXT, "num_turns": 1, "total_cost_usd": 0.02}]
    result, proc = _cli(tmp_path, monkeypatch, rows, budget)
    assert proc.closed and result["final"] == LIMIT_TEXT
    with pytest.raises(GatewayOperationError) as failed:
        _settle_budget(result, budget)
    assert failed.value.code == "AGENT_FALSE_SUCCESS"
    outcome = derive_run_outcome([{"sequence": 0, "kind": "failure", "record_sha256": "0" * 64,
                                   "payload": {"run_budget": budget.report()}}],
                                 terminal_state="failed")["budget"]
    assert outcome["false_success_signals"] == ["rate_limit"]
    assert budget.report()["used"]["cost_micros"] == 20_000


def test_cli_tool_calls_past_the_limit_stop_the_session(tmp_path, monkeypatch):
    limits = {**resolve_limits({"max_steps": 3}), "tool_actions": 1}
    use = lambda i: {"type": "assistant", "message": {"id": "m1", "content": [  # noqa: E731
        {"type": "tool_use", "id": f"t{i}", "name": "Read", "input": {"file_path": "a"}}]}}
    with pytest.raises(RunBudgetExceeded) as stopped:
        _cli(tmp_path, monkeypatch, [use(1), use(2)], RunBudget(limits))
    assert stopped.value.limit == "tool_actions"
