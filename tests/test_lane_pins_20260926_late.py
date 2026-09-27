"""The late 2026-09-26 pins: relay 0.4.0, gather 1.9.0, mneme 0.5.0, canon 0.4.1.

Every place the branch pins one of these lanes agrees on the release: the
registry, the payload row, the relay submodule, descriptor and compiled
expectation, the notices and the canon context checks. The launch adapts to
what each release changed:

- relay 0.4.0 keeps its session store in a per-user folder unless
  RELAY_SESSION_DIR names one; the engine names ``<lane>/sessions``. Shell
  children and CLI tiers need exec, which the app never grants, so the child
  also starts with no RELAY_CHILD_ENV names and no unproven CLI allowed;
- gather 1.9.0 reads network, exec and credential grants from its launch; the
  app's main action (a local document, a corpus) needs none, so every gather
  grant starts empty whatever the engine's environment or an env_allow says;
- mneme 0.5.0 makes forget a two-step erase; it stays T2;
- canon 0.4.1 serves context purge on its context server, which applies a plan
  only when started with CANON_CONTEXT_MCP_PURGE=apply; the engine never
  passes that name to the context child.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
PINS = {"relay": ("0.4.0", "v0.4.0", "ac4d79877f19e3e4c439c15d4781c3896e2f33db"),
        "gather": ("1.9.0", "v1.9.0", "335452827727bdb76d577dd7e84313f987c2ab15"),
        "mneme": ("0.5.0", "v0.5.0", "c47215d357c014e1105e6c402c2318110d0fdd40"),
        "canon": ("0.4.1", "v0.4.1", "583e0ceea333ef6acfef492254b2b31a13baad5a")}
GATHER_GRANTS = ("GATHER_ALLOW_NETWORK", "GATHER_ALLOW_EXEC", "GATHER_AUTH_ENV_ALLOW",
                 "GATHER_CHILD_ENV")


@pytest.mark.parametrize("lane", sorted(PINS))
def test_registry_and_row_carry_the_pin(lane):
    version, tag, commit = PINS[lane]
    row = ROWS[lane]
    assert LANES[lane].version == version
    assert (row["owner_tag"], row["owner_commit"]) == (tag, commit)
    assert row["flywheel_registry_expected_version"] == version
    assert row["owner_project"]["version"] == version
    assert row["component_descriptor"]["version"] == version


def test_the_relay_expectation_descriptor_and_submodule_agree():
    from harness.bundled_lane_expectations import expected_bundled_lane
    relay = expected_bundled_lane("relay")
    assert (relay["version"], relay["source_commit"]) == PINS["relay"][::2]
    descriptor = json.loads((ROOT / "packaging" / "bundled-lanes" / "relay.json").read_text(
        encoding="utf-8"))
    assert (descriptor["version"], descriptor["source"]["commit"]) == PINS["relay"][::2]
    text = " ".join(descriptor["does_not_prove"])
    assert "relay 0.3.0" not in text and "relay 0.4.0" in text
    gitlink = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "path = relay" in gitlink


def test_the_notices_name_each_new_pin():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    for lane, (version, tag, commit) in PINS.items():
        assert f"{ROWS[lane]['registry_install_name']} {version} (lane {lane}), tag {tag} " \
               f"@ {commit[:12]}" in text


def test_the_canon_context_checks_name_the_new_pin():
    from scripts import check_installed_canon_context as installed
    assert installed.CANON_PIN == PINS["canon"][2]
    source = (ROOT / "scripts" / "check_frozen_gateway.py").read_text(encoding="utf-8")
    assert PINS["canon"][2] in source and PINS["canon"][2] == ROWS["canon"]["owner_commit"]


def _confined(lane, tmp_path, environ_extra=None, row=None):
    from harness.lane_env import confine_lane_launch
    home = tmp_path / "home"
    environ = {"FLYWHEEL_HOME": str(home), "PATH": "C:/Windows/System32",
               **(environ_extra or {})}
    launch = LaunchSpec(("engine.exe", "--bundled-lane-mcp", lane), inherit_env=False)
    confined, _ = confine_lane_launch(LANES[lane], launch, environ, row or {})
    return dict(confined.env_overrides), home / "lanes" / lane


def test_relay_keeps_its_sessions_in_the_lane_folder(tmp_path):
    env, folder = _confined("relay", tmp_path)
    assert env["RELAY_SESSION_DIR"] == str(folder / "sessions")
    assert (folder / "sessions").is_dir()
    assert (env["RELAY_ALLOW_WRITE"], env["RELAY_ALLOW_EXEC"]) == ("0", "0")


def test_relay_children_and_cli_tiers_get_nothing_from_the_engine_or_a_grant(tmp_path):
    extra = {"RELAY_CHILD_ENV": "OPENAI_API_KEY", "RELAY_ALLOW_EXEC_CLI": "claude"}
    env, _folder = _confined("relay", tmp_path, extra,
                             {"env_allow": ["RELAY_CHILD_ENV", "RELAY_ALLOW_EXEC_CLI"]})
    assert env["RELAY_CHILD_ENV"] == "" and env["RELAY_ALLOW_EXEC_CLI"] == ""


def test_an_operator_session_folder_still_wins(tmp_path):
    chosen = str(tmp_path / "my-sessions")
    env, _folder = _confined("relay", tmp_path, {"RELAY_SESSION_DIR": chosen})
    assert env["RELAY_SESSION_DIR"] == chosen


def test_gather_starts_with_no_launch_grant(tmp_path):
    extra = {"GATHER_ALLOW_NETWORK": "all", "GATHER_ALLOW_EXEC": "python",
             "GATHER_AUTH_ENV_ALLOW": "GATHER_API_TOKEN@example.com",
             "GATHER_CHILD_ENV": "OPENAI_API_KEY"}
    env, _folder = _confined("gather", tmp_path, extra, {"env_allow": list(GATHER_GRANTS)})
    assert {name: env.get(name) for name in GATHER_GRANTS} == dict.fromkeys(GATHER_GRANTS, "")


def test_a_pip_gather_launch_starts_with_no_launch_grant(tmp_path):
    from harness.lane_env import confine_lane_launch
    environ = {"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "",
               "GATHER_ALLOW_NETWORK": "all"}
    launch = LaunchSpec(("python.exe", "-m", "gather.cli", "mcp"))
    confined, _ = confine_lane_launch(LANES["gather"], launch, environ,
                                      {"env_allow": ["GATHER_ALLOW_NETWORK"]})
    assert dict(confined.env_overrides)["GATHER_ALLOW_NETWORK"] == ""


def test_relay_session_ids_are_plain_ids(tmp_path, monkeypatch):
    from harness.lane_tier_gate import argument_refusal
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    for bad in ("../outside/private", "C:/Users/x/ledger", "a/b"):
        refused = argument_refusal("relay", "local_agent_sessions", {"session_id": bad})
        assert refused and refused["reason"] == "argument_refused", bad
    assert argument_refusal("relay", "local_agent_sessions", {"session_id": "abc-1"}) is None
    assert argument_refusal("relay", "local_agent_sessions", {}) is None


def test_mneme_forget_stays_t2_as_a_two_step_erase():
    entry = policy.tool_policy("mneme", "mneme.forget")
    assert entry.tier == "T2" and "mneme.forget" not in policy.admitted_tools("mneme")
    assert "confirm_plan_sha256" in entry.reason and "known finding 4" not in entry.reason


def test_the_canon_context_child_never_gets_the_purge_switch(tmp_path, monkeypatch):
    from harness.canon_context_runtime import context_mcp_environment
    import harness.lanes as lanes
    registry = tmp_path / "lanes.json"
    registry.write_text(json.dumps({"canon": {"env_allow": ["CANON_CONTEXT_MCP_PURGE"]}}),
                        encoding="utf-8")
    monkeypatch.setattr(lanes, "LANE_REGISTRY_PATH", registry)
    env = context_mcp_environment({"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "",
                                   "CANON_CONTEXT_MCP_PURGE": "apply"},
                                  str(tmp_path / "context.db"))
    assert not {k for k in env if k.upper() == "CANON_CONTEXT_MCP_PURGE"}


def test_a_pip_or_source_relay_launch_starts_its_mcp_server():
    """relay 0.3.0 gave ``python -m relay.local_mcp`` an argument parser that
    refuses ``--mcp``, so the pip and source argv exited 2 at launch. The engine
    starts ``python -m relay --mcp`` (relay's own CLI) and the frozen build still
    serves ``relay.local_mcp`` in process."""
    from harness.lane_runtime_support import pip_mcp_command
    lane = LANES["relay"]
    assert pip_mcp_command(lane, "python.exe", lambda _m: True) == [
        "python.exe", "-m", "relay", "--mcp"]
    assert lane.bundled_mcp_module == "relay.local_mcp"
    assert ROWS["relay"]["mcp"]["module"] == "relay.local_mcp"
