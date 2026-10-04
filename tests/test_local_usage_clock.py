"""Usage-capture tests must not depend on how fast the host runs.

test_local_router_records_indexed_usage_events_for_each_inner_call failed on a
Windows runner on 2026-10-03 with execution_state "timeout". The helper passed
a 3 s attempt budget measured by time.monotonic, and the loaded runner spent
those 3 s on two scripted inner calls plus tool execution. The same call takes
about 0.13 s on a quiet workstation. The helpers now pass a fixed clock, so the
attempt deadline is never measured in these tests. The checks below run the
helpers on a host slowed past a 1 s budget and expect a returned attempt.
"""
from __future__ import annotations

import dataclasses
import json
import time

import test_local_usage_capture as capture
from harness.cross_harness_adapters import FlywheelRouterAdapter, ProcessOutcome
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_types import AttemptRequest
from harness.cross_harness_usage import inner_source, usage_records_from_trace
from test_local_usage_capture import USAGE_A, USAGE_B, _final, _fixed_clock, _tool

SLOW_CALL_S = 0.6  # two calls take 1.2 s, past the 1 s budget below


class _SlowBackend(capture._ScriptedBackend):
    def chat(self, messages, **kwargs):
        time.sleep(SLOW_CALL_S)
        return super().chat(messages, **kwargs)


def test_router_helper_returns_on_a_host_slower_than_the_budget(tmp_path, monkeypatch):
    original = capture._request
    monkeypatch.setattr(capture, "_ScriptedBackend", _SlowBackend)
    monkeypatch.setattr(capture, "_request",
                        lambda root: dataclasses.replace(original(root), timeout_seconds=1))
    result, backend = capture._router(tmp_path, _tool(USAGE_A), _final("done", USAGE_B))
    assert backend.calls == 2
    assert result.execution_state == "returned", result.failure_detail


def _codex_outputs():
    def event(usage):
        return json.dumps({"type": "turn.completed", "model": "spark", "usage": usage})
    return [
        ProcessOutcome(0, "\n".join((event(USAGE_A), json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message",
                                                "text": 'TOOL read_file {"path":"x"}'}}))), "", 1, False),
        ProcessOutcome(0, "\n".join((event(USAGE_B), json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message",
                                                "text": "done"}}))), "", 1, False),
    ]


def _codex_request(root, timeout_seconds):
    return AttemptRequest(
        "run", "spark", "set", "agt-001-task", "prompt", "a" * 64,
        "flywheel_harness", "flywheel", "flywheel_router/v1", "spark", "spark",
        root, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1,
        "cold_declared", timeout_seconds, root,
    )


def test_codex_adapter_gives_its_clock_to_the_inner_proposer(tmp_path):
    # The adapter's clock already drove the outer deadline; the inner Codex
    # proposer kept time.monotonic, so an injected clock covered half the
    # attempt. The first call outlasts the 1 s budget on the real clock, so
    # the inner proposer refuses the second call unless it reads the
    # adapter's clock.
    outputs = _codex_outputs()
    (tmp_path / "x").write_text("evidence", encoding="utf-8")

    def runner(*_args, **_kwargs):
        if len(outputs) == 2:
            time.sleep(2 * SLOW_CALL_S)
        return outputs.pop(0)

    adapter = FlywheelRouterAdapter(runner=runner, executable_resolver=lambda: "codex.cmd",
                                    proposer_invocations_max=None, clock=_fixed_clock)
    result = adapter.execute(_codex_request(tmp_path, 1))
    assert result.execution_state == "returned", result.failure_detail
    assert usage_records_from_trace(result.tool_trace) == [USAGE_A, USAGE_B]


def test_codex_inner_usage_source_stays_codex_inner(tmp_path):
    outputs = _codex_outputs()
    (tmp_path / "x").write_text("evidence", encoding="utf-8")
    adapter = FlywheelRouterAdapter(
        runner=lambda *a, **k: outputs.pop(0),
        executable_resolver=lambda: "codex.cmd",
        proposer_invocations_max=None,
        clock=_fixed_clock,
    )

    result = adapter.execute(_codex_request(tmp_path, 3))

    assert inner_source(result.tool_trace) == "codex_inner"
    assert "local_endpoint_inner" not in {event.get("source") for event in result.tool_trace}
    assert usage_records_from_trace(result.tool_trace) == [USAGE_A, USAGE_B]
