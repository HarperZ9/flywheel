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

from harness.evidence_json import canonical_sha256
from harness.gateway_run_outcome import derive_run_outcome
from harness.run_budget import DEFAULTS, OVERRIDE_BOUNDS

ROOT = Path(__file__).resolve().parents[1]
DART = ROOT / "desktop" / "lib" / "models" / "rowan_run_budget.dart"
FIXTURE = ROOT / "tests" / "fixtures" / "gateway_run_outcome" / "stopped_projection.json"


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
