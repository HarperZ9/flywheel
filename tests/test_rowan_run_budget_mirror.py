"""The desktop shows the engine's run-budget defaults, and parses its outcome.

The engine owns the limits (harness/run_budget.py). The desktop only mirrors
the defaults and ranges to show them as hints before a run starts, so a
drift between the two would show the owner one number and enforce another.
The shared fixture is the other half: the Dart test parses it and recomputes
its projection hash, so both languages agree on one derived block.
"""
import json
import re
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_execution import _settle_budget
from harness.gateway_cli_events import NativeEvents
from harness.gateway_run_outcome import derive_run_outcome
from harness.run_budget import (DEFAULTS, OVERRIDE_BOUNDS, RunBudget, RunBudgetExceeded,
                                resolve_limits)

ROOT = Path(__file__).resolve().parents[1]
DART = ROOT / "desktop" / "lib" / "models" / "rowan_run_budget.dart"
FIXTURE = ROOT / "tests" / "fixtures" / "gateway_run_outcome" / "stopped_projection.json"
CLI_FIXTURE = ROOT / "tests" / "fixtures" / "gateway_run_outcome" / "cli_streamed_spend.json"


def _dart_constant(name: str) -> str:
    match = re.search(rf"static const {name} = ([^;]+);", DART.read_text(encoding="utf-8"))
    assert match, f"{name} is missing from the desktop mirror"
    return match.group(1).strip()


def test_desktop_defaults_match_the_engine():
    assert int(_dart_constant("defaultToolActions")) == DEFAULTS["max_tool_actions"]
    assert int(_dart_constant("defaultUsageTokens")) == DEFAULTS["max_usage_tokens"]
    assert int(_dart_constant("defaultCostMicros")) == DEFAULTS["max_cost_micros"]


def test_desktop_ranges_match_the_engine():
    for dart, key in (("toolActionsRange", "max_tool_actions"),
                      ("usageTokensRange", "max_usage_tokens"),
                      ("costMicrosRange", "max_cost_micros")):
        low, high = (int(v) for v in _dart_constant(dart).strip("()").split(","))
        assert (low, high) == OVERRIDE_BOUNDS[key], dart


def test_the_shared_fixture_is_what_the_engine_derives():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    projection = data["projection"]
    assert projection["run_outcome"] == derive_run_outcome(
        data["records"], terminal_state=projection["state"])
    body = {k: v for k, v in projection.items() if k != "projection_sha256"}
    assert canonical_sha256(body) == projection["projection_sha256"]


def cli_session_block(events: list) -> dict:
    """The budget block a Claude CLI session's events derive, stopped on spend."""
    budget = RunBudget(resolve_limits({"max_steps": 6}), clock=lambda: 0.0)
    reader = NativeEvents("claude-cli", ["Read"], lambda event: None, max_steps=6,
                          budget=budget)
    for event in events:
        reader.feed(json.dumps(event))
    with pytest.raises(RunBudgetExceeded):
        _settle_budget({"final": reader.finish()["final"]}, budget)
    records = [{"sequence": 0, "kind": "failure", "record_sha256": "0" * 64,
                "payload": {"run_budget": budget.report()}}]
    return derive_run_outcome(records, terminal_state="failed")["budget"]


def test_the_cli_spend_fixture_is_what_the_engine_derives():
    # Each message streamed its usage, so the result's cost is the session's
    # only report of spend. The Dart card test reads this block, so the card
    # line it checks is the one these events produce.
    data = json.loads(CLI_FIXTURE.read_text(encoding="utf-8"))
    assert data["budget"] == cli_session_block(data["events"])
    assert data["budget"]["reporting"] == {"calls_with_tokens": 2, "calls_without_tokens": 0,
                                           "calls_with_cost": 2}
