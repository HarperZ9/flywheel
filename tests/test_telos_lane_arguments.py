"""telos takes no argument, and the engine passes it none.

Every tool telos 0.6.0 serves declares an inputSchema with no property and
``additionalProperties`` false, and its server never reads a call's arguments.
The engine keeps that true for any later release: each telos tool passes no
argument on the lane call and Plugins routes, and an agent run, which passes
the model's arguments through, cannot select a telos tool. The committed
measurement is bound to the pinned tarball, so a re-pin fails here until the
tools are measured again, and a release whose served schema gains a property
fails until the policy lists it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.lane_tier_gate import (
    agent_tool_refusal, guard_args, lane_policy_review, plugin_refusal)
from harness.lane_tool_policy import admitted_tools, lane_policy
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "project-docs" / "lanes" / "evidence"
            / "telos-0.6.0-tool-measurement.json")
PAYLOADS = ROOT / "packaging" / "node-lane-payloads.json"
# Names the package's own CLI scripts read (--out, --gh-run, --scan-root) and
# the kinds of value the engine guards elsewhere: a path, a URL, a command, an id.
HOSTILE = {"path": "C:/Windows/System32/config/SAM", "--out": "../../escape.json",
           "--gh-run": "owner/repo#1", "--scan-root": "C:/", "url": "http://127.0.0.1:9/",
           "command": "calc.exe", "sessionId": "../../x"}
TELOS = sorted(lane_policy("telos"))
T2 = ("telos.room", "telos.workflow", "telos.proof", "telos.native.control")


def _row() -> dict:
    lanes = json.loads(PAYLOADS.read_text(encoding="utf-8"))["lanes"]
    return next(row for row in lanes if row["lane"] == "telos")


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("tool", TELOS)
def test_the_engine_passes_a_telos_tool_no_argument(tool):
    assert lane_policy("telos")[tool].allowed_args == ()
    sent = dict(HOSTILE)
    assert guard_args("telos", tool, sent) == {}
    assert sent == HOSTILE   # the caller's dict is not changed


def test_the_approval_sheet_shows_every_sent_argument_as_dropped():
    review = lane_policy_review({"name": "telos", "tool": "telos.proof", "args": HOSTILE,
                                 "governance_tier": "T2"})
    assert review["required_tier"] == "T2"
    assert review["arguments"] == {}
    assert review["dropped_arguments"] == sorted(HOSTILE)
    assert review["requested_arguments"] == HOSTILE


@pytest.mark.parametrize("tool", TELOS)
def test_an_agent_run_cannot_select_a_telos_tool(tool):
    assert agent_tool_refusal("telos", "lane", (tool,)) == "CAPABILITY_NOT_ADMITTED"


def test_plugins_reach_the_t1_telos_tools_and_no_t2_one():
    admitted = admitted_tools("telos")
    assert len(admitted) == 37
    assert [tool for tool in admitted if plugin_refusal("telos", tool) is not None] == []
    for tool in T2:
        assert plugin_refusal("telos", tool) is not None, tool


def test_the_measurement_is_of_the_pinned_tarball_and_covers_every_tool():
    evidence, row = _evidence(), _row()
    assert evidence["tarball_sha256"] == row["sha256"]
    assert evidence["package"] == f"project-telos-mcp {LANES['telos'].version}"
    assert row["version"] == LANES["telos"].version
    served = sorted(row["static_tool_names"])
    assert sorted(evidence["served_input_schemas"]) == served
    assert set(evidence["runs"]) == {"system_path", "full_path", "stand_ins_beside_package"}
    for name, run in evidence["runs"].items():
        assert sorted(run["tools"]) == served, name
        assert run["package_unchanged"] is True, name
        assert run["lane_files_left"] == [], name


def test_no_served_schema_declares_an_argument_the_policy_drops():
    for tool, schema in _evidence()["served_input_schemas"].items():
        allowed = lane_policy("telos")[tool].allowed_args
        assert set(schema.get("properties") or {}) <= set(allowed or ()), tool
        assert schema.get("additionalProperties") is False, tool
