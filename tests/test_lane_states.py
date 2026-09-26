"""The lane state a card shows comes from the engine, and a health answer
alone never reads as "Runs" (H-2).

Each case builds the three inputs the state is computed from, all local and
fake: a roster row (runtime selection), a probe record (what the last probe
found) and setup checks (Node, Git, the model server, keys). One case per
state, then the regressions the plan names: a health-only lane is never
ready, a record from an earlier engine session reads "Last checked", and a
call that could not launch rewrites the row.
"""
from __future__ import annotations

import pytest

from harness.lane_probe_cache import ProbeCache, lane_pin
from harness.lane_roster_row import STATES, by_state, lane_state, roster_rows
from harness.lane_setup import SetupChecks
from harness.tool_discovery import ToolFinding

ENGINE = "9.9.9"
NOW = "2026-09-26T12:00:00Z"


def _cache(tmp_path, engine=ENGINE):
    return ProbeCache(tmp_path / "state" / "lane-probes.json", engine=engine,
                      clock=lambda: NOW)


def _checks(tmp_path, *, git=True, model=False, node=True):
    home = tmp_path / "home"
    finding = lambda tool, ok: ToolFinding(  # noqa: E731
        tool, ok, f"C:/tools/{tool}.exe" if ok else None, "v22.1.0" if ok else None,
        "user_path" if ok else "not_found", "", "fake")
    return SetupChecks(
        {"FLYWHEEL_HOME": str(home)},
        node=lambda: finding("node", node), git=lambda: finding("git", git),
        model_health=lambda: {"any_live": model, "tiers": [
            {"backend": "ollama", "healthy": model, "detail": "x"}]},
        key_source=lambda _name: "absent", key_grants=lambda _lane: (),
        validated_keys=lambda _lane: set())


def _row(lane, *, status="declared", codes=()):
    return {"name": lane, "status": status, "detail": "", "blocking_codes": list(codes)}


def _answered(cache, lane, tools):
    cache.record(lane, lane_pin(lane), "answered", tools=tools)


def test_every_state_is_named_once():
    assert STATES == ("not_checked", "ready", "limited", "needs_setup", "reads_only",
                      "cannot_launch", "unreachable")


def test_not_checked_when_no_probe_ran(tmp_path):
    state = lane_state("gather", _row("gather"), cache=_cache(tmp_path),
                       checks=_checks(tmp_path))
    assert state["state"] == "not_checked"
    assert state["sentence"] == "Not checked yet."
    assert state["last_checked"] is None


def test_ready_needs_a_listed_main_tool_with_its_needs_met(tmp_path):
    cache = _cache(tmp_path)
    _answered(cache, "gather", ["gather.status", "gather.docs", "gather.context"])
    state = lane_state("gather", _row("gather"), cache=cache, checks=_checks(tmp_path))
    assert state["state"] == "ready"
    assert state["sentence"].startswith("Runs catalog a local document")
    assert state["checked_line"] == f"Checked {NOW}."
    assert state["checked_this_session"] is True


def test_limited_names_the_item_other_tools_wait_on(tmp_path):
    cache = _cache(tmp_path)
    _answered(cache, "index", ["index.map", "index.symbol-definition",
                               "index.symbol-references", "index.doctor"])
    state = lane_state("index", _row("index"), cache=cache,
                       checks=_checks(tmp_path, git=False))
    assert state["state"] == "limited"
    assert state["waiting_tools"] == ["index.map"]
    assert [item["id"] for item in state["setup"]] == ["git"]
    assert "1 tools need: Git for Windows" in state["sentence"]


def test_needs_setup_when_no_main_tool_can_run_and_says_health_answered(tmp_path):
    cache = _cache(tmp_path)
    _answered(cache, "relay", ["relay.status", "relay.doctor", "local_agent_run"])
    state = lane_state("relay", _row("relay"), cache=cache,
                       checks=_checks(tmp_path, model=False))
    assert state["state"] == "needs_setup"
    assert state["sentence"].startswith("Start a model server")
    assert "127.0.0.1:11434" in state["sentence"] and "127.0.0.1:8765" in state["sentence"]
    assert state["second_line"] == "Answers its health check."
    assert not state["sentence"].startswith("Runs")


def test_needs_setup_from_a_runtime_setup_code_names_the_item(tmp_path):
    state = lane_state("local-model", _row(
        "local-model", status="missing", codes=("local_model_root_unset",)),
        cache=_cache(tmp_path), checks=_checks(tmp_path))
    assert state["state"] == "needs_setup"
    assert [item["id"] for item in state["setup"]] == ["project_folder"]
    assert state["sentence"] == "Choose a project folder."


def test_reads_only_for_a_class_c_lane(tmp_path):
    state = lane_state("calibrate-pro", _row("calibrate-pro"), cache=_cache(tmp_path),
                       checks=_checks(tmp_path))
    assert state["state"] == "reads_only"
    assert "Calibration runs in Calibrate Pro itself" in state["sentence"]


def test_cannot_launch_from_a_defect_code_or_a_failed_probe(tmp_path):
    blocked = lane_state("forum", _row("forum", status="missing",
                                       codes=("bundled_payload_missing",)),
                         cache=_cache(tmp_path), checks=_checks(tmp_path))
    assert (blocked["state"], blocked["code"]) == ("cannot_launch", "bundled_payload_missing")
    assert blocked["sentence"] == "Could not start: bundled_payload_missing."
    cache = _cache(tmp_path)
    cache.record("chorus", lane_pin("chorus"), "cannot_launch", code="mcp_probe_failed")
    probed = lane_state("chorus", _row("chorus"), cache=cache, checks=_checks(tmp_path))
    assert (probed["state"], probed["code"]) == ("cannot_launch", "mcp_probe_failed")


def test_unreachable_names_the_url(tmp_path):
    cache = _cache(tmp_path)
    cache.record("bulletin", lane_pin("bulletin"), "unreachable", code="network_error")
    state = lane_state("bulletin", _row("bulletin"), cache=cache, checks=_checks(tmp_path))
    assert state["state"] == "unreachable"
    assert state["sentence"].startswith("Cannot reach http")


def test_a_health_only_lane_is_never_ready(tmp_path):
    """The H-2 regression: status and doctor answer, no main tool is listed."""
    cache = _cache(tmp_path)
    _answered(cache, "crucible", ["crucible.status", "crucible.doctor"])
    state = lane_state("crucible", _row("crucible", status="live"), cache=cache,
                       checks=_checks(tmp_path))
    assert state["state"] != "ready"
    assert not state["sentence"].startswith("Runs")
    assert state["code"] == "main_tool_not_admitted"


def test_a_record_from_an_earlier_session_reads_last_checked(tmp_path):
    _answered(_cache(tmp_path), "gather", ["gather.docs"])
    later = _cache(tmp_path)  # a new engine session reads the same file
    state = lane_state("gather", _row("gather"), cache=later, checks=_checks(tmp_path))
    assert state["state"] == "ready"
    assert state["checked_this_session"] is False
    assert state["checked_line"] == f"Last checked {NOW}."


def test_a_record_under_another_engine_version_is_not_used(tmp_path):
    _answered(_cache(tmp_path, engine="1.0.4"), "gather", ["gather.docs"])
    state = lane_state("gather", _row("gather"), cache=_cache(tmp_path),
                       checks=_checks(tmp_path))
    assert state["state"] == "not_checked"


def test_a_call_that_could_not_launch_rewrites_the_row(tmp_path, monkeypatch):
    """H-10: the lane call route records LANE_CANNOT_LAUNCH on the card's row."""
    import harness.lane_call_route as route
    import harness.lane_caller as caller
    import harness.lane_probe_cache as probes
    cache = _cache(tmp_path)
    _answered(cache, "gather", ["gather.docs"])
    monkeypatch.setattr(probes, "default_cache", lambda environ=None: cache)
    monkeypatch.setattr(caller, "call_lane_tool", lambda *a, **k: {
        "error": "lane 'gather' unavailable: MCPError: server closed the connection"})
    body, status = route.handle_lane_call("/api/lane/gather/gather.docs", {})
    assert (status, body["code"]) == (503, "LANE_CANNOT_LAUNCH")
    state = lane_state("gather", _row("gather"), cache=cache, checks=_checks(tmp_path))
    assert (state["state"], state["code"]) == ("cannot_launch", "server_exited")


def test_roster_rows_record_a_probe_and_count_by_state(tmp_path):
    cache = _cache(tmp_path)
    probed = {"name": "gather", "status": "live", "detail": "gather.status answered",
              "blocking_codes": [], "tool_names": ["gather.docs", "gather.status"]}
    failed = {"name": "chorus", "status": "declared", "blocking_codes": [],
              "detail": "MCP probe failed: mcp_probe_failed (cannot launch)"}
    rows = roster_rows([probed, failed], probed=True, cache=cache, checks=_checks(tmp_path))
    assert [r["state"] for r in rows] == ["ready", "cannot_launch"]
    counts = by_state(rows)
    assert counts["ready"] == 1 and counts["cannot_launch"] == 1
    assert sum(counts.values()) == 2


@pytest.mark.parametrize("lane", ["gather", "index", "relay", "canon", "bulletin"])
def test_a_poll_without_a_probe_keeps_the_probed_state(tmp_path, lane):
    """The D1 regression at the engine: a later unprobed roster keeps the row."""
    cache = _cache(tmp_path)
    tools = {"gather": ["gather.docs"], "index": ["index.symbol-definition"],
             "relay": ["local_agent_run"], "canon": ["canon.validate"],
             "bulletin": ["board_rooms"]}[lane]
    _answered(cache, lane, tools)
    first = roster_rows([_row(lane)], probed=False, cache=cache, checks=_checks(tmp_path))
    second = roster_rows([_row(lane)], probed=False, cache=cache, checks=_checks(tmp_path))
    assert first[0]["state"] == second[0]["state"] != "not_checked"
