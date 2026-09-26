"""What a lane card says, checked against what the build can do.

The honesty review found cards that claimed more than the build runs: forum's
"run a deliberation room" on an echo executor, "1 tools", writing's diagnose
read as ready with no draft, the bulletin identity copy pointing at the wrong
screen, and no probe test that produces the tool list the ready state reads.
"""
from __future__ import annotations

from harness.lane_probe_cache import ProbeCache, lane_pin
from harness.lane_roster_row import lane_state
from tests.test_lane_states import _answered, _cache, _checks, _row


def test_forum_says_what_the_echo_executor_does_and_names_real_rooms_untested(tmp_path):
    cache = _cache(tmp_path)
    _answered(cache, "forum", ["forum.route", "plan", "forum.status"])
    state = lane_state("forum", _row("forum"), cache=cache, checks=_checks(tmp_path))
    assert state["state"] == "ready"
    assert state["sentence"] == ("Ready to route and plan a request with no model. "
                                 "Real rooms: after setup, untested.")


def test_writing_needs_a_recorded_draft_and_says_the_call_is_t2(tmp_path):
    cache = _cache(tmp_path)
    _answered(cache, "writing", ["writing.status", "writing.doctor"])
    checks = _checks(tmp_path)
    state = lane_state("writing", _row("writing"), cache=cache, checks=checks)
    assert state["state"] == "needs_setup"
    assert state["sentence"] == "Record a draft on the Writing screen first."
    body = (tmp_path / "home" / "state" / "artifacts" / "writing" / "v1" / "owners" / "o"
            / "projects" / "p" / "body")
    body.mkdir(parents=True)
    (body / "rev_1.txt").write_text("draft", encoding="utf-8")
    ready = lane_state("writing", _row("writing"), cache=cache, checks=_checks(tmp_path))
    assert ready["state"] == "ready"
    assert ready["sentence"] == "Ready to diagnose a draft on a call you approve at T2."


def test_a_limited_lane_pluralizes(tmp_path):
    from harness.lane_roster_row import _plural
    assert _plural(1, "other tool needs", "other tools need") == "1 other tool needs"
    assert _plural(3, "other tool needs", "other tools need") == "3 other tools need"


def test_calibrate_pro_carries_its_slice_in_the_version(tmp_path):
    row = {**_row("calibrate-pro"), "expected_version": "2.0.0"}
    state = lane_state("calibrate-pro", row, cache=_cache(tmp_path), checks=_checks(tmp_path))
    assert state["version_label"] == "2.0.0 (catalog slice)"
    other = lane_state("gather", {**_row("gather"), "expected_version": "1.8.2"},
                       cache=_cache(tmp_path), checks=_checks(tmp_path))
    assert "version_label" not in other


def test_the_bulletin_identity_copy_names_the_keys_panel(tmp_path):
    item = _checks(tmp_path).item("bulletin_identity", "bulletin")
    assert not item.met
    assert "Keys panel on the Endpoints screen" in item.copy
    assert "Bulletin screen" not in item.copy


def test_a_probe_that_lists_a_main_tool_produces_a_ready_row(tmp_path, monkeypatch):
    """C14: the probe itself writes the tool list the ready state reads."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.lane_roster_row import roster_rows

    class _Client:
        server_info = {"name": "plexus", "version": "0.2.2"}

        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def list_tools(self):
            return [{"name": "plexus.status"}, {"name": "plexus_route"},
                    {"name": "plexus_plan"}]

        def call_text(self, _tool, _args):
            return {"ok": True, "text": '{"ok": true, "version": "0.2.2"}'}

    monkeypatch.setattr(mcp_client, "MCPClient", _Client)
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_importable", lambda name: True)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: lane.version)
    row = lanes.lane_status("plexus", probe=True, timeout=1.0)
    assert {"plexus_route", "plexus_plan"} <= set(row["tool_names"])
    cache = ProbeCache(tmp_path / "probes.json", engine="9.9.9")
    [state] = roster_rows([row], probed=True, cache=cache, checks=_checks(tmp_path))
    assert state["state"] == "ready", state
    assert cache.lookup("plexus", lane_pin("plexus"))[0]["tools"]
