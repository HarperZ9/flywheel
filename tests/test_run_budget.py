"""The run budget refuses the step past a limit, and reads exit-0 limit errors."""
from dataclasses import dataclass

import pytest

from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.limit_signal import PATTERN_NAMES, limit_signal
from harness.run_budget import (BUDGET_EXHAUSTED, DEFAULTS, RunBudget,
                                RunBudgetExceeded, resolve_limits,
                                validate_run_budget_request)
from harness.run_budget_contract import SIGNALS


@dataclass
class Result:
    name: str
    args: dict
    ok: bool
    output: str


class Recorder:
    """An executor double that counts what actually ran."""

    def __init__(self, output="listing", ok=True):
        self.calls, self.output, self.ok, self.root = [], output, ok, "."

    def execute(self, name, args, rationale=None):
        self.calls.append(name)
        return Result(name, args, self.ok, self.output)


def limits(**over):
    base = {"model_calls": 3, "tool_actions": 2, "usage_tokens": 1_000,
            "cost_micros": 500_000, "limit_signals": 2, "wall_time_ms": 60_000}
    return {**base, **over}


@pytest.mark.parametrize("text,kind", [
    ("Claude AI usage limit reached|1760000000", "rate_limit"),
    ("Error: HTTP 429 Too Many Requests", "rate_limit"),
    ("You've hit your limit. It will reset at 5pm.", "rate_limit"),
    ('{"error": {"type": "insufficient_quota"}}', "quota"),
    ("Your credit balance is too low to access the API.", "billing"),
    ("Invalid API key. Please run /login", "auth"),
    ('{"type": "error", "error": {"type": "overloaded_error"}}', "overloaded"),
])
def test_limit_signal_reads_each_kind_of_limit_error(text, kind):
    assert limit_signal(text) == kind


@pytest.mark.parametrize("text", [
    "All 12 tests passed.", "", None, "see line 429 of parser.py",
    "error: file not found", "401 lines changed",
    # A long log that quotes a phrase only in its middle is not a failure.
    "ok\n" * 400 + "docs mention rate limit exceeded handling\n" + "ok\n" * 400,
])
def test_limit_signal_leaves_ordinary_output_alone(text):
    assert limit_signal(text) is None


def test_signal_vocabulary_matches_the_shared_contract():
    assert PATTERN_NAMES == SIGNALS


def test_tool_action_past_the_limit_is_refused_before_it_runs():
    inner = Recorder()
    executor = RunBudget(limits(tool_actions=2)).wrap_executor(inner)
    executor.execute("list_dir", {"path": "."})
    executor.execute("list_dir", {"path": "."})
    with pytest.raises(RunBudgetExceeded) as stopped:
        executor.execute("list_dir", {"path": "."})
    assert stopped.value.code == BUDGET_EXHAUSTED and stopped.value.limit == "tool_actions"
    assert inner.calls == ["list_dir", "list_dir"]


def test_model_call_past_the_limit_is_refused():
    budget = RunBudget(limits(model_calls=1))
    budget.charge_model_call()
    with pytest.raises(RunBudgetExceeded):
        budget.charge_model_call()
    report = budget.report()
    assert report["status"] == "stopped" and report["tripped"] == "model_calls"
    assert report["used"]["model_calls"] == 1


def test_exit_zero_with_a_limit_error_is_recorded_as_failed():
    inner = Recorder(output="Claude AI usage limit reached|1760000000")
    budget = RunBudget(limits(tool_actions=10))
    result = budget.wrap_executor(inner).execute("run", {"cmd": "claude -p hi"})
    assert result.ok is False
    assert result.output.startswith("[flywheel] the step exited 0")
    assert budget.report()["false_success_count"] == 1


def test_file_content_that_quotes_a_limit_is_not_a_failed_step():
    inner = Recorder(output="rate limit exceeded")
    budget = RunBudget(limits(tool_actions=10))
    result = budget.wrap_executor(inner).execute("read_file", {"path": "notes.md"})
    assert result.ok is True and budget.report()["false_success_count"] == 0


def test_repeated_limit_errors_trip_the_breaker_at_the_next_step():
    inner = Recorder(output="Error: 429 Too Many Requests")
    executor = RunBudget(limits(tool_actions=10)).wrap_executor(inner)
    executor.execute("run", {"cmd": "retry"})
    executor.execute("run", {"cmd": "retry"})
    with pytest.raises(RunBudgetExceeded) as stopped:
        executor.execute("run", {"cmd": "retry"})
    assert stopped.value.limit == "limit_signals" and len(inner.calls) == 2


def test_tokens_crossing_the_limit_stop_the_next_step_and_settle():
    budget = RunBudget(limits(usage_tokens=1_000))
    budget.charge_model_call()
    budget.record_usage({"prompt_tokens": 900, "completion_tokens": 300})
    with pytest.raises(RunBudgetExceeded) as stopped:
        budget.charge_tool_action()
    assert stopped.value.limit == "usage_tokens"
    last_call = RunBudget(limits(usage_tokens=1_000))
    last_call.record_usage({"total_tokens": 1_001})
    with pytest.raises(RunBudgetExceeded):
        last_call.settle()


def test_cost_counts_only_when_reported_and_says_so():
    budget = RunBudget(limits())
    budget.record_usage({"input_tokens": 10, "output_tokens": 5})
    budget.record_usage(None, cost_usd=0.25)
    report = budget.report()
    assert report["used"]["usage_tokens"] == 15 and report["used"]["cost_micros"] == 250_000
    assert report["reporting"] == {"calls_with_tokens": 1, "calls_without_tokens": 1,
                                   "calls_with_cost": 1}
    budget.record_usage(None, cost_usd=0.30)
    with pytest.raises(RunBudgetExceeded) as stopped:
        budget.settle()
    assert stopped.value.limit == "cost_micros"


def test_limits_resolve_from_defaults_and_owner_override():
    op = {"max_steps": 4, "timeout_s": 90}
    assert resolve_limits(op) == {
        "model_calls": 4, "tool_actions": DEFAULTS["max_tool_actions"],
        "usage_tokens": DEFAULTS["max_usage_tokens"],
        "cost_micros": DEFAULTS["max_cost_micros"], "limit_signals": 2,
        "wall_time_ms": 90_000}
    over = resolve_limits({**op, "run_budget": {"max_tool_actions": 0,
                                                "max_model_calls": 2}})
    assert over["tool_actions"] == 0 and over["model_calls"] == 2


@pytest.mark.parametrize("value", [
    {}, {"max_tool_actions": True}, {"max_tool_actions": 201},
    {"max_usage_tokens": 10}, {"max_spend": 5}, [], {"max_cost_micros": 1.5}])
def test_bad_overrides_are_refused(value):
    with pytest.raises(ValueError):
        validate_run_budget_request(value)


def _agent_op(**extra):
    return {"goal": "g", "endpoint": "ollama", "max_steps": 2, "allow_write": False,
            "allow_exec": False, "stream": True, "data_refs": [],
            "credential_refs": [], **extra}


def test_agent_run_operation_carries_a_valid_override_and_refuses_a_bad_one():
    accepted = canonicalize_operation(
        "agent.run", _agent_op(run_budget={"max_tool_actions": 5}))
    assert accepted.operation["run_budget"]["max_tool_actions"] == 5
    with pytest.raises(GatewayOperationError) as refused:
        canonicalize_operation("agent.run", _agent_op(run_budget={"max_tool_actions": -1}))
    assert refused.value.code == "INVALID_REQUEST"
