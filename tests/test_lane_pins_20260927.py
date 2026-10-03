"""The 2026-09-27 pins: gather 1.9.1, relay 0.5.0 and forum 1.15.1.

Each closes published advisories on the release the branch pinned before:

- gather 1.9.1 closes GHSA-j6j7-39vh-qrp4 (an MCP path argument could make
  Windows sign in to a share a model named) and GHSA-r38f-cr69-jpp8 (a PATH
  entry reaching the working folder could start a planted program);
- relay 0.5.0 closes GHSA-82fg-qprm-q5r7 (the same PATH route, git's own
  children and the bisect shell included);
- forum 1.15.1 closes GHSA-36gv-h885-fmjf (1.14.0 and earlier: approvals not
  bound to a raised gate, executors with the working folder and the whole
  environment, an open daemon) and GHSA-h6qh-49hv-4xcg (1.15.0's working-folder
  guard missed an alias, a repointed link and a quoted PATH entry).

Every pin site agrees on the release, and no release adds a lane tool, so the
policy table keeps its rows. forum's gate decision grant has its own tests
(tests/test_forum_gate_decision_grant.py), and so do the lane refusal codes
(tests/test_lane_refusal_codes.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
PINS = {"gather": ("2.1.0", "v2.1.0", "d37814eee1295b1773ee9c86c8892a1dde739293"),
        "relay": ("0.6.0", "v0.6.0", "2510d6b3db9c42074c1139af21155a6bf8187b62"),
        "forum": ("1.16.0", "v1.16.0", "2acc4e3b3ac2a43bdc2210f998bb2a533c4bd5d9")}
REPLACED = {"gather": "1.9.0", "relay": "0.4.0", "forum": "1.14.0"}
ADVISORIES = {"gather": ("GHSA-j6j7-39vh-qrp4", "GHSA-r38f-cr69-jpp8"),
              "relay": ("GHSA-82fg-qprm-q5r7",),
              "forum": ("GHSA-36gv-h885-fmjf", "GHSA-h6qh-49hv-4xcg")}


@pytest.mark.parametrize("lane", sorted(PINS))
def test_registry_and_row_carry_the_pin(lane):
    version, tag, commit = PINS[lane]
    row = ROWS[lane]
    assert LANES[lane].version == version
    assert (row["owner_tag"], row["owner_describe"], row["owner_commit"]) == (tag, tag, commit)
    assert row["flywheel_registry_expected_version"] == version
    assert row["owner_project"]["version"] == version
    assert row["owner_project"]["imported_version"] == version
    assert row["component_descriptor"]["version"] == version
    assert row["component_descriptor"]["source"]["commit"] == commit


@pytest.mark.parametrize("lane", sorted(PINS))
def test_no_new_lane_tool_enters_with_the_pin(lane):
    served = set(ROWS[lane]["mcp"]["static_tool_names"])
    assert served == set(policy.lane_policy(lane))
    assert ROWS[lane]["component_descriptor"]["allowed_tools"] == policy.admitted_tools(lane)
    assert ROWS[lane]["mcp"]["allowed_tools_for_initial_admission"] == \
        policy.admitted_tools(lane)


def test_the_forum_row_still_lists_the_tools_a_granted_launch_serves():
    """forum 1.15 lists its three gate decision tools only on a granted launch;
    the row names every tool the lane serves on some launch the engine makes,
    and admits none of the three."""
    row = ROWS["forum"]
    decisions = {"gate_approve", "gate_edit", "gate_reject"}
    assert decisions <= set(row["mcp"]["static_tool_names"])
    assert not decisions & set(row["component_descriptor"]["allowed_tools"])


def test_the_relay_submodule_descriptor_and_expectation_agree():
    from harness.bundled_lane_expectations import expected_bundled_lane
    version, _tag, commit = PINS["relay"]
    relay = expected_bundled_lane("relay")
    assert (relay["version"], relay["source_commit"]) == (version, commit)
    descriptor = json.loads((ROOT / "packaging" / "bundled-lanes" / "relay.json").read_text(
        encoding="utf-8"))
    assert (descriptor["version"], descriptor["source"]["commit"]) == (version, commit)
    text = " ".join(descriptor["does_not_prove"])
    assert "relay 0.6.0" in text and "relay 0.4.0" not in text
    assert "no shell, bisect or git child starts" in text
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("no git checkout to read the relay gitlink from")
    staged = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "relay"],
                            capture_output=True, text=True, check=True).stdout.split()
    assert staged[:2] == ["160000", commit]


def test_the_notices_name_each_new_pin_and_drop_the_old():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    for lane, (version, tag, commit) in PINS.items():
        name = ROWS[lane]["registry_install_name"]
        assert f"{name} {version} (lane {lane}), tag {tag} @ {commit[:12]}" in text
        assert f"{name} {REPLACED[lane]} (lane {lane})" not in text


def test_the_release_notes_name_each_advisory_as_fixed():
    notes = (ROOT / "RELEASE-NOTES-1.1.0.md").read_text(
        encoding="utf-8")
    fixes = notes.split("Security fixes in the lanes", 1)[1].split("\n## ", 1)[0]
    for lane, advisories in ADVISORIES.items():
        version = {"gather": "2.0.0", "relay": "0.5.0", "forum": "1.15.1"}[lane]
        assert f"{lane} {version}" in fixes, lane
        for advisory in advisories:
            assert advisory in fixes, advisory
    assert "relay 0.4.0, gather 1.9.0" not in notes
    assert "forum 1.14.0 ships" not in notes


@pytest.mark.parametrize("bundled", [True, False], ids=["frozen", "pip"])
def test_forum_starts_with_no_command_grants(tmp_path, bundled):
    """forum 1.15 reads FORUM_CHILD_ENV and FORUM_ALLOW_EXEC_CLI from its launch
    for the commands it starts. The engine's forum launch configures no command,
    and both names start empty whatever the environment or an env_allow says."""
    from harness.lane_env import confine_lane_launch
    from harness.mcp_client import LaunchSpec
    environ = {"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "C:/Windows/System32",
               "FORUM_CHILD_ENV": "OPENAI_API_KEY", "FORUM_ALLOW_EXEC_CLI": "gemini"}
    argv = (("engine.exe", "--bundled-lane-mcp", "forum") if bundled
            else ("python.exe", "-m", "forum.cli", "mcp"))
    launch = LaunchSpec(argv, inherit_env=not bundled)
    confined, _ = confine_lane_launch(
        LANES["forum"], launch, environ,
        {"env_allow": ["FORUM_CHILD_ENV", "FORUM_ALLOW_EXEC_CLI"]})
    env = dict(confined.env_overrides)
    assert (env["FORUM_CHILD_ENV"], env["FORUM_ALLOW_EXEC_CLI"]) == ("", "")
    assert "--allow-gate-decisions" not in confined.argv
