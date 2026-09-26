"""Bound runs are stopped by real limit errors and not by ordinary output.

These drive the real router path and the real CLI event parser. Only the
provider transport, and for CLI sessions the process, are synthetic.
"""
import json
import sys
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import _settle_budget, run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_cli_events import NativeEvents
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.gateway_run_outcome import derive_run_outcome
from harness.plan_run_snapshot import thaw_json
from harness.run_budget import RunBudget, RunBudgetExceeded, resolve_limits
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_gateway_run_budget import _cli


def _drive(tmp_path, monkeypatch, operation, replies):
    """The real router path with commands run bare, so pytest really runs."""
    state = tmp_path.parent / (tmp_path.name + "_state")
    state.mkdir(exist_ok=True)
    prompts = []

    def factory(**authority):
        def transport(method, url, headers, body, timeout):
            prompts.append(json.loads(body)["messages"][-1]["content"])
            text = replies[min(len(prompts) - 1, len(replies) - 1)]
            return 200, {"model": authority["model"],
                         "choices": [{"message": {"content": text}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    monkeypatch.setattr("harness.router_agent.make_sandboxed_runner", lambda **kw: None)
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", operation), state))
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION)
    try:
        run_private_agent(operation, {}, state, trace, None, lambda e: None,
                          binding=binding, deadline=time.monotonic() + 120)
        error = None
    except GatewayOperationError as exc:
        error = exc
    return error, AgentTrace(state, OWNER, JOURNEY, OPERATION).read(), prompts


def _op(tmp_path, **extra):
    return {"goal": "add retry with backoff on 429", "endpoint": "ollama",
            "model": "qwen2.5-coder:14b", "root": str(tmp_path), "max_steps": 6,
            "allow_write": True, "allow_exec": True, "stream": True,
            "data_refs": [], "credential_refs": [], **extra}


def _pytest(name):
    return f'"{sys.executable}" -m pytest -vv -p no:cacheprovider -o addopts= {name}'


def test_a_passing_check_whose_test_ids_name_limits_completes(tmp_path, monkeypatch):
    (tmp_path / "test_client.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('msg', ['rate limit exceeded', 'quota exceeded'])\n"
        "def test_client_maps_error(msg):\n    assert msg\n", encoding="utf-8")
    error, records, prompts = _drive(tmp_path, monkeypatch,
                                     _op(tmp_path, test_cmd=_pytest("test_client.py")),
                                     ["The client already handles this. Done."])
    assert error is None and records[-1]["kind"] == "result"
    assert len(prompts) == 1
    report = records[-1]["payload"]["run_budget"]
    assert report["status"] == "within_limits" and report["false_success_count"] == 0
    assert records[-1]["payload"]["completion"]["verdict"] == "verified"


def test_a_final_answer_that_describes_429_handling_completes(tmp_path, monkeypatch):
    replies = ['TOOL write_file {"path": "client.py", "content": "RETRY_ON = (429,)"}',
               "Added exponential backoff so the client retries when the API returns "
               "HTTP 429 Too Many Requests, and a 401 for an invalid API key is not retried."]
    error, records, _ = _drive(tmp_path, monkeypatch, _op(tmp_path, allow_exec=False), replies)
    assert error is None and records[-1]["kind"] == "result"
    assert records[-1]["payload"]["run_budget"]["false_success_steps"] == []


def test_failing_checks_that_quote_a_401_do_not_trip_the_breaker(tmp_path, monkeypatch):
    (tmp_path / "test_login.py").write_text(
        "def test_login():\n    status = 401\n"
        "    assert status == 200, f'got {status} Unauthorized'\n", encoding="utf-8")
    run = f'TOOL run {{"cmd": {json.dumps(_pytest("test_login.py"))}}}'
    replies = [run, 'TOOL write_file {"path": "notes.txt", "content": "try"}', run,
               'TOOL write_file {"path": "notes.txt", "content": "again"}', "Stuck on it."]
    error, records, _ = _drive(tmp_path, monkeypatch, _op(tmp_path), replies)
    assert error is None
    report = records[-1]["payload"]["run_budget"]
    assert report["tripped"] is None and report["limit_signal_steps"] == []


def _assistant(ident, *tools):
    return {"type": "assistant", "message": {"id": ident, "content": [
        {"type": "tool_use", "id": t, "name": "Read", "input": {"file_path": "a"}}
        for t in tools]}}


def _result(**extra):
    return {"type": "result", "is_error": False, "subtype": "success", "result": "done",
            "num_turns": 1, **extra}


def test_claude_cli_cache_tokens_count_against_the_token_limit(tmp_path, monkeypatch):
    budget = RunBudget(resolve_limits({"max_steps": 3}))
    usage = {"input_tokens": 12, "cache_creation_input_tokens": 40_000,
             "cache_read_input_tokens": 900_000, "output_tokens": 2_000}
    result, _ = _cli(tmp_path, monkeypatch,
                     [_assistant("m1"), _result(usage=usage, total_cost_usd=0.5)], budget)
    assert budget.report()["used"]["usage_tokens"] == 942_012
    with pytest.raises(RunBudgetExceeded) as stopped:
        _settle_budget(result, budget)
    assert stopped.value.limit == "usage_tokens"


def test_an_errored_cli_result_still_records_what_it_spent(tmp_path, monkeypatch):
    budget = RunBudget(resolve_limits({"max_steps": 3}))
    rows = [_assistant("m1"), _result(is_error=True, subtype="error_max_turns",
                                      total_cost_usd=4.25,
                                      usage={"input_tokens": 300_000, "output_tokens": 20_000})]
    with pytest.raises(GatewayOperationError) as failed:
        _cli(tmp_path, monkeypatch, rows, budget)
    assert failed.value.code == "AGENT_CLI_INCOMPLETE"
    report = budget.report()
    assert report["used"]["cost_micros"] == 4_250_000
    assert report["used"]["usage_tokens"] == 320_000


def test_an_errored_run_over_its_limits_is_recorded_as_stopped(tmp_path, monkeypatch):
    from harness.gateway_agent_execution import _record_failure
    for usage, cost, limit in (({"input_tokens": 300_000, "output_tokens": 20_000}, None,
                                "usage_tokens"), (None, 4.25, "cost_micros")):
        budget = RunBudget(resolve_limits({"max_steps": 3}))
        rows = [_assistant("m1"), _result(is_error=True, subtype="error_max_turns",
                                          total_cost_usd=cost, usage=usage)]
        with pytest.raises(GatewayOperationError) as failed:
            _cli(tmp_path, monkeypatch, rows, budget)
        (tmp_path / limit).mkdir()
        trace = AgentTrace(tmp_path / limit, OWNER, JOURNEY, OPERATION)
        _record_failure(trace, failed.value, budget)
        records = AgentTrace(tmp_path / limit, OWNER, JOURNEY, OPERATION).read()
        report = records[-1]["payload"]["run_budget"]
        assert (report["status"], report["tripped"]) == ("stopped", limit)
        derived = derive_run_outcome(records, terminal_state="failed")["budget"]
        assert (derived["status"], derived["tripped"]) == ("stopped", limit)


def test_a_cli_session_stopped_before_its_result_names_unreported_calls(tmp_path, monkeypatch):
    limits = {**resolve_limits({"max_steps": 3}), "tool_actions": 2}
    budget = RunBudget(limits)
    rows = [_assistant("m1", "t1"), _assistant("m2", "t2"), _assistant("m3", "t3")]
    with pytest.raises(RunBudgetExceeded):
        _cli(tmp_path, monkeypatch, rows, budget)
    report = budget.report()
    assert report["used"]["model_calls"] == 3
    assert report["reporting"]["calls_without_tokens"] == 3


def _codex(budget, rows):
    parser = NativeEvents("codex-cli", ["command_execution"], lambda e: None,
                          max_steps=6, budget=budget)
    for row in rows:
        parser.feed(json.dumps(row))
    return parser.finish()


def _command(ident, output, exit_code=0):
    return {"type": "item.completed", "item": {"id": ident, "type": "command_execution",
            "command": "x", "aggregated_output": output, "exit_code": exit_code}}


def _codex_rows(*items, usage=None):
    return [{"type": "thread.started"}, {"type": "turn.started"}, *items,
            {"type": "item.completed", "item": {"id": "am", "type": "agent_message",
                                                "text": "done"}},
            {"type": "turn.completed", "usage": usage or {}}]


def test_codex_reported_usage_reaches_the_budget():
    budget = RunBudget({**resolve_limits({"max_steps": 6}), "usage_tokens": 1_000})
    result = _codex(budget, _codex_rows(_command("c1", "ok"), usage={
        "input_tokens": 500_000, "cached_input_tokens": 400_000, "output_tokens": 90_000}))
    report = budget.report()
    assert report["used"]["usage_tokens"] == 590_000 and report["used"]["model_calls"] == 1
    with pytest.raises(RunBudgetExceeded):
        _settle_budget(result, budget)


def test_codex_commands_that_echo_limit_words_do_not_stop_the_session():
    budget = RunBudget(resolve_limits({"max_steps": 6}))
    commit = "[fix/client 3f2a1b9] Retry on HTTP 429 from the upstream API\n 1 file changed"
    jest = ("PASS  src/client.test.ts\n  ✓ backs off when rate limited (4 ms)\n"
            "Tests:       2 passed, 2 total")
    _codex(budget, _codex_rows(_command("c1", commit), _command("c2", jest),
                               _command("c3", commit), usage={"input_tokens": 5}))
    assert budget.report()["status"] == "within_limits"


def test_codex_refuses_limits_it_cannot_observe(tmp_path):
    from harness.gateway_cli_binding import _request
    base = {"goal": "g", "endpoint": "codex-cli", "model": "gpt-6-astra",
            "execution_mode": "native_cli_session", "max_steps": 3, "allow_write": False,
            "allow_exec": True, "stream": True, "data_refs": [], "credential_refs": []}
    for limit in ({"max_model_calls": 1}, {"max_cost_micros": 10_000}):
        op = canonicalize_operation("agent.run", {**base, "run_budget": limit}).operation
        with pytest.raises(GatewayOperationError) as refused:
            _request(op)
        assert refused.value.code == "AGENT_CLI_BUDGET_UNSUPPORTED"
    _request(canonicalize_operation(
        "agent.run", {**base, "run_budget": {"max_usage_tokens": 5_000}}).operation)


def _failure(report):
    return [{"sequence": 0, "kind": "failure", "record_sha256": "0" * 64,
             "payload": {"error_type": "RunBudgetExceeded", "run_budget": report}}]


def test_a_report_that_hides_unreported_model_calls_is_unverifiable():
    budget = RunBudget(resolve_limits({"max_steps": 3}))
    budget.used["model_calls"] = 2
    report = budget.report()
    report["reporting"]["calls_without_tokens"] = 0
    derived = derive_run_outcome(_failure(report), terminal_state="failed")["budget"]
    assert derived["reason"] == "BUDGET_HIDES_UNREPORTED_CALLS"


def test_a_limit_signal_stop_must_name_the_steps_that_tripped_it():
    budget = RunBudget(resolve_limits({"max_steps": 3}))
    budget.tripped = "limit_signals"
    derived = derive_run_outcome(_failure(budget.report()), terminal_state="failed")["budget"]
    assert derived["reason"] == "BUDGET_STOP_NOT_SUPPORTED"
    budget.limit_signal_steps = [{"tool": "run", "signal": "quota", "action": i,
                                  "match": "insufficient_quota"} for i in (1, 2)]
    derived = derive_run_outcome(_failure(budget.report()), terminal_state="failed")["budget"]
    assert derived["limit_signal_steps"] == [
        {"tool": "run", "signal": "quota", "match": "insufficient_quota"}] * 2
