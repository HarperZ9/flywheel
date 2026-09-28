"""Argument guards and the key rule, on the lane call, Plugins and agent-run routes.

POLICY-DECISION C-1 to C-8, C-11, C-12 and C-14, and security finding S1. Each
test drives the real gate with a fake MCP client, so nothing is spawned; a
refusal must happen before any child would start.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from harness import lane_tool_policy as policy
from harness.mcp_client import LaunchSpec
from tests.test_lane_tier_enforcement import (  # noqa: F401  (fixture)
    _Recorder, _call, _catalog_lane, _plugin_lane, lane_calls)

_WIDEN = {"root": "C:/", "check": "whoami", "test_cmd": "pytest", "online": True,
          "allow_write": True, "allow_exec": True, "an_argument_added_later": 1}


def test_relay_run_passes_only_its_listed_arguments_and_forces_the_rest(lane_calls):
    args = {"goal": "g", "max_steps": 1, **_WIDEN}
    assert _call("relay", "local_agent_run", args) == {"ok": True}
    sent = lane_calls.calls[-1][2]
    assert sent == {"goal": "g", "max_steps": 1, "allow_write": False,
                    "allow_exec": False, "online": False}


def test_plugins_apply_the_same_relay_filter(monkeypatch):
    recorder = _Recorder()
    call = _plugin_lane(monkeypatch, recorder, "relay")
    call("local_agent_run", {"goal": "g", **_WIDEN})
    assert recorder.calls[-1][2] == {"goal": "g", "allow_write": False,
                                     "allow_exec": False, "online": False}


@pytest.mark.parametrize("lane,tool,args,sent", [
    ("relay", "local_agent_chat", {"prompt": "p", "backend": "auto", "online": True,
                                   "model": "m"},
     {"prompt": "p", "backend": "auto", "online": False}),
    ("relay", "local_agent_health", {"online": True, "x": 1}, {"online": False}),
    ("local-model", "local_agent_health", {"online": True}, {"online": False}),
    ("local-model", "local_agent_chat", {"prompt": "p", "online": True},
     {"prompt": "p", "online": False}),
    ("local-model", "local_agent_run", {"goal": "g", **_WIDEN, "root": "sub"},
     {"goal": "g", "root": "sub", "allow_write": False, "allow_exec": False,
      "online": False}),
])
def test_online_tiers_are_forced_off_on_both_agent_lanes(lane_calls, lane, tool, args, sent):
    assert _call(lane, tool, args) == {"ok": True}
    assert lane_calls.calls[-1][2] == sent


def test_the_allowlists_are_the_reviewed_ones():
    assert policy.tool_policy("relay", "local_agent_run").allowed_args == (
        "goal", "max_steps", "max_tokens", "model", "backend", "compact_budget")
    assert policy.tool_policy("relay", "local_agent_chat").allowed_args == ("prompt", "backend")
    assert policy.tool_policy("local-model", "local_agent_run").allowed_args == (
        "goal", "root", "max_steps", "max_tokens", "backend")
    assert policy.tool_policy("relay", "local_agent_health").allowed_args == ()


@pytest.mark.parametrize("tool,name", [("learn_tutor_plan", "sessionId"),
                                        ("learn_tutor_mastery", "sessionId"),
                                        ("learn_verify", "runId"),
                                        ("learn_receipt", "runId")])
@pytest.mark.parametrize("bad", ["../../../lanes", "a/b", "..", "x" * 65, "", 7])
def test_an_id_that_could_leave_the_lane_folder_is_refused_before_spawn(
        lane_calls, tool, name, bad):
    result = _call("learn", tool, {name: bad})
    assert result["code"] == "LANE_TOOL_ERROR"
    assert result["reason"] == "argument_refused"
    assert lane_calls.calls == []


def test_a_plain_id_passes(lane_calls):
    assert _call("learn", "learn_tutor_plan", {"sessionId": "abc-1", "topic": "t"}) == {
        "ok": True}


def test_writing_never_receives_a_home_and_diagnose_needs_t2(lane_calls):
    _call("writing", "writing.status", {"home": "C:/elsewhere"})
    assert lane_calls.calls[-1][2] == {}
    denied = _call("writing", "writing.diagnose", {"revision_ref": "r"})
    assert denied.get("governance_denied") is True
    assert _call("writing", "writing.diagnose", {"revision_ref": "r", "home": "x"},
                 tier="T2") == {"ok": True}
    assert lane_calls.calls[-1][2] == {"revision_ref": "r"}


def test_actuation_is_out_of_this_build_even_on_a_t2_call(lane_calls):
    result = _call("accountable-surface", "accountable-surface.actuate", {}, tier="T2")
    assert result["code"] == "NOT_IN_BUILD"
    assert result["reason"] == "actuation_outside_app"
    assert lane_calls.calls == []


class _Bindings:
    """A bound credential set, as the grant path hands it to the lane caller."""

    def child_environment(self, _base, platform="windows"):
        return {"OPENAI_API_KEY": "planted-fake-key-value"}

    def redact(self, text):
        return text.replace("planted-fake-key-value", "[redacted]")


def test_a_t1_call_that_would_bind_a_key_needs_t2(lane_calls):
    from harness.lane_caller import call_lane_tool
    result = call_lane_tool("mneme", "mneme.remember", {"session": "s", "turns": []},
                            credential_bindings=_Bindings())
    assert result.get("governance_denied") is True
    assert lane_calls.calls == []


def test_a_t1_child_gets_no_key_shaped_name_from_env_allow(lane_calls, monkeypatch):
    import harness.lanes as lanes
    import harness.lane_credentials as creds
    base = LaunchSpec(("engine.exe", "--bundled-lane-mcp", "mneme"), inherit_env=False,
                      env_overrides=(("OPENAI_API_KEY", "v"), ("OPENAI_MODEL", "m"),
                                     ("PATH", "C:/Windows/System32")),
                      allowed_tools=tuple(policy.admitted_tools("mneme")))
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: base)
    monkeypatch.setattr(creds, "lane_key_grants", lambda lane, registry=None: (
        "OPENAI_API_KEY", "OPENAI_MODEL"))
    _call("mneme", "mneme.remember", {"session": "s", "turns": []})
    env = dict(lane_calls.calls[-1][0].env_overrides)
    assert "OPENAI_API_KEY" not in env
    assert env["OPENAI_MODEL"] == "m"
    _call("mneme", "mneme.remember", {"session": "s", "turns": []}, tier="T2")
    assert dict(lane_calls.calls[-1][0].env_overrides)["OPENAI_API_KEY"] == "v"


def test_plugins_refuse_a_lane_tool_the_table_does_not_list(monkeypatch):
    recorder = _Recorder()
    call = _plugin_lane(monkeypatch, recorder, "gather")
    result = call("gather.a_tool_added_later", {})
    assert result["code"] == "CAPABILITY_NOT_ADMITTED"
    assert recorder.calls == []


@pytest.mark.parametrize("catalog,tool", [
    ("gather", "gather.a_tool_added_later"),       # C-11 unlisted
    ("mneme", "mneme.remember"),                   # C-12 state_write
    ("accountable-surface", "accountable-surface.perceive"),  # C-12 open egress
    ("gather", "gather.docs"),                     # C-12 path argument
    ("index", "index.symbol-definition"),          # C-12 path argument
    ("learn", "learn_tutor_mastery"),              # id guard
])
def test_an_agent_run_refuses_the_narrower_set(monkeypatch, tmp_path, catalog, tool):
    from harness.gateway_agent_mcp_cache import restricted_catalog_launch
    from harness.gateway_operation import GatewayOperationError
    _catalog_lane(monkeypatch, tmp_path)
    with pytest.raises(GatewayOperationError, match="CAPABILITY_NOT_ADMITTED"):
        restricted_catalog_launch(catalog, [tool])


def test_a_path_into_the_engine_home_is_refused_outside_the_lane_folder(
        lane_calls, monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    for target in (home / "gateway.token", home / "keys" / "signing.key",
                   home / "lanes.json", home / "lanes" / "mneme" / "mneme.db", home):
        result = _call("gather", "gather.docs", {"path": str(target)})
        assert result.get("reason") == "argument_refused", target
    assert lane_calls.calls == []
    inside = home / "lanes" / "gather" / "note.md"
    assert _call("gather", "gather.docs", {"path": str(inside)}) == {"ok": True}
    outside = tmp_path / "project" / "note.md"
    assert _call("gather", "gather.docs", {"path": str(outside)}) == {"ok": True}
    relative = "../../gateway.token"   # resolved from the lane folder
    assert _call("gather", "gather.docs", {"path": relative}).get(
        "reason") == "argument_refused"


def test_every_path_argument_names_a_real_argument_of_a_listed_tool():
    for lane, tools in policy.LANE_TOOL_POLICY.items():
        for name, entry in tools.items():
            assert isinstance(entry.path_args, tuple) and isinstance(entry.id_args, tuple)
            assert not (set(entry.path_args) & set(entry.id_args)), (lane, name)


def test_guard_args_filters_before_it_forces():
    entry = policy.tool_policy("relay", "local_agent_run")
    assert entry.forced_args
    guarded = policy.guard_args("relay", "local_agent_run", {"goal": "g", "online": True})
    assert guarded == {"goal": "g", "allow_write": False, "allow_exec": False,
                       "online": False}
    plain = replace(entry, allowed_args=None, forced_args=())
    assert plain.allowed_args is None
