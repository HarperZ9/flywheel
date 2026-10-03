"""The 2026-09-26 boundaries, retained through the articulate 0.6.0 repin.

relay 0.3.0 and canon 0.3.0 were pinned here first; relay 0.4.0 and canon
0.4.1 replaced them the same day (tests/test_lane_pins_20260926_late.py).
The relay descriptor keeps the launch-grant boundary this file checked.

- articulate 0.5.0 reads the claude CLI path from ARTICULATE_CLAUDE_CLI, so
  judge, fix and polish are in the build at T2 behind the ``claude_cli`` item,
  and the engine passes the CLI it found to the articulate child only.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
PINS = {"articulate": ("0.6.0", "v0.6.0", "36f7e9f1f027f400b4839ec7394d64823ed1ac1d")}


def test_registry_rows_and_expectations_carry_each_pin():
    from harness.bundled_lane_expectations import expected_bundled_lane
    for lane, (version, tag, commit) in PINS.items():
        row = ROWS[lane]
        assert LANES[lane].version == version, lane
        assert (row["owner_tag"], row["owner_commit"]) == (tag, commit), lane
        assert row["flywheel_registry_expected_version"] == version, lane
    assert expected_bundled_lane("relay")["allowed_tools"] == tuple(
        policy.admitted_tools("relay"))


def test_the_relay_descriptor_names_the_launch_grant_boundary():
    descriptor = json.loads((ROOT / "packaging" / "bundled-lanes" / "relay.json").read_text(
        encoding="utf-8"))
    text = " ".join(descriptor["does_not_prove"])
    assert "still reads both from tool arguments" not in text
    assert "launch" in text and "root, check" in text


def test_articulate_model_tools_are_t2_behind_the_claude_item():
    for tool in ("judge", "fix", "polish"):
        entry = policy.tool_policy("articulate", tool)
        assert (entry.tier, entry.not_in_build, entry.effect) == ("T2", "", "spend")
        assert entry.needs == ("claude_cli",)
        assert tool not in policy.admitted_tools("articulate")


def test_claude_discovery_prefers_the_variable_then_an_exe_then_a_shim(tmp_path):
    from harness.claude_discovery import find_claude
    exe_dir, shim_dir = tmp_path / "bin", tmp_path / "npm"
    exe_dir.mkdir()
    shim_dir.mkdir()
    (shim_dir / "claude.cmd").write_text("@echo off", encoding="utf-8")
    none = lambda _scope: None  # noqa: E731
    env = {"PATH": f"{shim_dir};{exe_dir}", "APPDATA": str(tmp_path)}
    assert find_claude(env, read_registry_path=none, platform="nt").path == str(
        shim_dir / "claude.cmd")
    (exe_dir / "claude.exe").write_bytes(b"")
    assert find_claude(env, read_registry_path=none, platform="nt").path == str(
        exe_dir / "claude.exe")
    pinned = tmp_path / "pinned" / "claude.exe"
    pinned.parent.mkdir()
    pinned.write_bytes(b"")
    found = find_claude({**env, "ARTICULATE_CLAUDE_CLI": str(pinned)},
                        read_registry_path=none, platform="nt")
    assert (found.found, found.source) == (True, "ARTICULATE_CLAUDE_CLI")
    relative = find_claude({**env, "ARTICULATE_CLAUDE_CLI": "claude.exe"},
                           read_registry_path=none, platform="nt")
    assert not relative.found
    assert not find_claude({"PATH": ""}, read_registry_path=none, platform="nt").found


def test_the_claude_item_states_the_login_it_cannot_check(tmp_path):
    from harness.lane_setup import SetupChecks
    from harness.tool_discovery import ToolFinding
    found = ToolFinding("claude", True, "C:/bin/claude.exe", None, "user_path", "", "x")
    item = SetupChecks({"FLYWHEEL_HOME": str(tmp_path)}, claude=lambda: found).item(
        "claude_cli", "articulate")
    assert item.met and "claude login" in item.copy and "not checked" in item.copy
    missing = ToolFinding("claude", False, None, None, "not_found", "", "x")
    item = SetupChecks({"FLYWHEEL_HOME": str(tmp_path)}, claude=lambda: missing).item(
        "claude_cli", "articulate")
    assert not item.met and "ARTICULATE_CLAUDE_CLI" in item.copy


def test_only_the_articulate_child_receives_the_claude_path(tmp_path, monkeypatch):
    import harness.claude_discovery as discovery
    from harness.lane_env import confine_lane_launch
    from harness.tool_discovery import ToolFinding
    found = ToolFinding("claude", True, "C:/bin/claude.exe", None, "user_path", "", "x")
    monkeypatch.setattr(discovery, "find_claude", lambda environ, **_k: found)
    environ = {"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "C:/Windows/System32"}
    for lane, expect in (("articulate", "C:/bin/claude.exe"), ("gather", None)):
        launch = LaunchSpec(("engine.exe", "--bundled-lane-mcp", lane), inherit_env=False)
        confined, _ = confine_lane_launch(LANES[lane], launch, environ, {})
        assert dict(confined.env_overrides).get("ARTICULATE_CLAUDE_CLI") == expect, lane
