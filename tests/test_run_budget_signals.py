"""What counts toward the limit-signal breaker, and what the budget reports.

A passing check, a failed step and a mention in ordinary output never trip
the breaker. Provider usage that arrives in cache fields, on a failed
request, or never, is still named in the report.
"""
import pytest

from harness.gateway_operation import GatewayOperationError
from harness.run_budget import RunBudget, RunBudgetExceeded
from tests.test_limit_signal import PYTEST_IDS
from tests.test_run_budget import Recorder, limits

ANCHORED = "Error: 429 Too Many Requests"


def test_the_runs_own_check_command_is_charged_but_not_read():
    inner = Recorder(output="lots of output\n" + ANCHORED)
    budget = RunBudget(limits(tool_actions=10))
    executor = budget.wrap_executor(inner, test_cmd="pytest -q")
    for _ in range(3):
        result = executor.execute("run", {"cmd": "pytest -q"})
        assert result.ok is True and result.output == inner.output
    report = budget.report()
    assert report["used"]["tool_actions"] == 3
    assert report["false_success_count"] == 0 and report["limit_signal_steps"] == []


def test_a_passing_verbose_test_log_that_names_limit_cases_is_left_alone():
    inner = Recorder(output=PYTEST_IDS)
    budget = RunBudget(limits(tool_actions=10))
    executor = budget.wrap_executor(inner)
    for _ in range(3):
        assert executor.execute("run", {"cmd": "pytest -vv"}).ok is True
    report = budget.report()
    assert report["status"] == "within_limits" and report["limit_signal_steps"] == []
    assert report["false_success_count"] == 3
    assert {s["counted"] for s in report["false_success_steps"]} == {False}


def test_nonzero_exit_steps_do_not_count_toward_the_breaker():
    inner = Recorder(output="E  AssertionError: got 401 Unauthorized\n" + ANCHORED, ok=False)
    budget = RunBudget(limits(tool_actions=10))
    executor = budget.wrap_executor(inner)
    for _ in range(4):
        assert executor.execute("run", {"cmd": "pytest"}).ok is False
    report = budget.report()
    assert report["status"] == "within_limits" and report["false_success_count"] == 0


def test_a_file_write_between_two_signals_ends_the_run_of_counted_steps():
    budget = RunBudget(limits(tool_actions=10))
    signal = budget.wrap_executor(Recorder(output=ANCHORED))
    write = budget.wrap_executor(Recorder(output="wrote a.py"))
    signal.execute("run", {"cmd": "curl"})
    write.execute("write_file", {"path": "a.py"})
    signal.execute("run", {"cmd": "curl"})
    write.execute("write_file", {"path": "a.py"})
    report = budget.report()
    assert report["status"] == "within_limits"
    assert [s["action"] for s in report["limit_signal_steps"]] == [1, 3]


def test_two_counted_steps_in_a_row_trip_and_the_report_names_them():
    executor = RunBudget(limits(tool_actions=10)).wrap_executor(Recorder(output=ANCHORED))
    executor.execute("run", {"cmd": "curl"})
    executor.execute("run", {"cmd": "curl"})
    with pytest.raises(RunBudgetExceeded) as stopped:
        executor.execute("run", {"cmd": "curl"})
    assert stopped.value.limit == "limit_signals"
    steps = executor._budget.report()["limit_signal_steps"]
    assert [(s["tool"], s["signal"], s["match"]) for s in steps] == [
        ("run", "rate_limit", "status 429")] * 2


def test_anthropic_cache_tokens_count_toward_the_token_limit():
    budget = RunBudget(limits(usage_tokens=200_000))
    budget.record_usage({"input_tokens": 12, "cache_creation_input_tokens": 40_000,
                         "cache_read_input_tokens": 900_000, "output_tokens": 2_000})
    assert budget.report()["used"]["usage_tokens"] == 942_012
    with pytest.raises(RunBudgetExceeded) as stopped:
        budget.settle()
    assert stopped.value.limit == "usage_tokens"


def test_subset_cache_counters_are_not_added_twice():
    budget = RunBudget(limits())
    budget.record_usage({"input_tokens": 500, "cached_input_tokens": 400, "output_tokens": 10})
    budget.record_usage({"prompt_tokens": 50, "completion_tokens": 5,
                         "prompt_tokens_details": {"cached_tokens": 40}})
    assert budget.report()["used"]["usage_tokens"] == 565


def test_a_provider_request_that_raises_is_named_as_unreported():
    budget = RunBudget(limits(model_calls=3))

    def transport(*args):
        raise GatewayOperationError("EXTERNAL_ACTION_FAILED")
    with pytest.raises(GatewayOperationError):
        budget.guard_transport(transport)("POST", "u", {}, b"", 5)
    report = budget.report()
    assert report["used"]["model_calls"] == 1
    assert report["reporting"]["calls_without_tokens"] == 1


def test_model_calls_no_report_covered_are_named_as_unreported():
    budget = RunBudget(limits(model_calls=5))
    for _ in range(3):
        budget.count_observed("model_calls")
    report = budget.report()
    assert report["reporting"] == {"calls_with_tokens": 0, "calls_without_tokens": 3,
                                   "calls_with_cost": 0}
    budget.record_usage({"total_tokens": 90}, calls=budget.unaccounted_calls())
    assert budget.report()["reporting"]["calls_with_tokens"] == 3
    assert budget.report()["reporting"]["calls_without_tokens"] == 0
