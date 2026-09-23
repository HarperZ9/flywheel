"""A Claude CLI session's tokens are counted as its messages stream.

claude 2.1.251 puts a `usage` object on every assistant event's message
(input_tokens, output_tokens, cache_creation_input_tokens,
cache_read_input_tokens) and again on the final result event, for the whole
session. One message can arrive as several assistant events with the same
message id. So each message counts once, by id, and the result event adds
only what the messages did not already report. A session stopped before its
result still reports what its messages used.
"""
import json

import pytest

from harness.gateway_cli_events import NativeEvents
from harness.run_budget import RunBudget, RunBudgetExceeded, resolve_limits

USAGE = {"input_tokens": 12, "output_tokens": 30, "cache_creation_input_tokens": 400,
         "cache_read_input_tokens": 5_000, "service_tier": "standard"}
PER_MESSAGE = 5_442


def _message(ident, *tools, usage=USAGE):
    return {"type": "assistant", "message": {
        "id": ident, "model": "claude-haiku-4-5-20251001", "usage": usage,
        "content": [{"type": "tool_use", "id": t, "name": "Read",
                     "input": {"file_path": "a"}} for t in tools]
        or [{"type": "text", "text": "done"}]}}


def _result(usage, cost=0.01):
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
            "result": "done", "usage": usage, "total_cost_usd": cost}


def _feed(budget, rows):
    parser = NativeEvents("claude-cli", ["Read"], lambda e: None, max_steps=6, budget=budget)
    for row in rows:
        parser.feed(json.dumps(row))
    return parser


def test_a_session_stopped_mid_run_reports_the_tokens_its_messages_streamed():
    budget = RunBudget({**resolve_limits({"max_steps": 6}), "tool_actions": 1})
    with pytest.raises(RunBudgetExceeded):
        _feed(budget, [_message("m1", "t1"), _message("m2", "t2")])
    report = budget.report()
    assert report["used"]["usage_tokens"] == 2 * PER_MESSAGE
    assert report["reporting"]["calls_with_tokens"] == 2
    assert report["reporting"]["calls_without_tokens"] == 0


def test_a_message_split_over_several_events_and_the_result_count_once():
    budget = RunBudget(resolve_limits({"max_steps": 6}))
    total = {"input_tokens": 24, "output_tokens": 70, "cache_creation_input_tokens": 800,
             "cache_read_input_tokens": 10_000}
    # m1 arrives twice (one event per content block), then m2, then the result.
    _feed(budget, [_message("m1", "t1"), _message("m1", "t2"), _message("m2"), _result(total)])
    report = budget.report()
    assert report["used"]["usage_tokens"] == 10_894
    assert report["used"]["model_calls"] == 2
    assert report["reporting"]["calls_with_tokens"] == 2
    assert report["used"]["cost_micros"] == 10_000


def test_streamed_tokens_past_the_limit_stop_the_session_at_the_next_step():
    budget = RunBudget({**resolve_limits({"max_steps": 6}), "usage_tokens": 5_000})
    with pytest.raises(RunBudgetExceeded) as stopped:
        _feed(budget, [_message("m1", "t1"), _message("m2", "t2")])
    # m1's tokens cross the limit, so the session stops at m1's tool call.
    assert stopped.value.limit == "usage_tokens"
    assert budget.report()["used"]["tool_actions"] == 0
    assert budget.report()["used"]["model_calls"] == 1
