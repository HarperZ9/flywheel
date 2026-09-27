"""Lane children run with trace capture off.

The capture hooks read FLYWHEEL_CAPTURE from their own environment. A hook that
a claude or codex CLI fires inside a lane child (articulate's judge, a relay CLI
tier) inherits the lane child's environment, so without this rule the owner's
custody would record a lane's internal calls as the owner's turns. The lane
layer sets FLYWHEEL_CAPTURE=off for every spawned lane child and every other
child that runs lane code, whatever the engine's environment or the launch says.
"""
from __future__ import annotations

import os

import pytest

from capture_channel_fixture import RecordingListener, run_hook, spool_files, stop_event
from harness.lane_env import confine_lane_launch, lane_process_environment
from harness.lane_workdir import CAPTURE_OFF, forced_env, pin_lane_workdir
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parent(tmp_path, **extra) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "FLYWHEEL_HOME": str(tmp_path / "home"),
           "FLYWHEEL_CAPTURE": "on"}
    for name in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "HOME",
                 "USERPROFILE", "LANG"):
        if name in os.environ:
            env[name] = os.environ[name]
    env.update(extra)
    return env


def test_the_rule_is_capture_off():
    assert CAPTURE_OFF == {"FLYWHEEL_CAPTURE": "off"}


@pytest.mark.parametrize("lane", sorted(LANES))
def test_every_lane_forces_capture_off(lane, tmp_path):
    assert forced_env(lane, tmp_path / "lane", {})["FLYWHEEL_CAPTURE"] == "off"


@pytest.mark.parametrize("inherit", [True, False])
def test_a_spawned_lane_child_starts_with_capture_off(tmp_path, inherit):
    launch = LaunchSpec(("python", "-I", "-m", "mneme.cli", "mcp"),
                        env_overrides=(("FLYWHEEL_CAPTURE", "on"),), inherit_env=inherit)
    pinned = pin_lane_workdir(LANES["mneme"], launch, _parent(tmp_path))
    assert dict(pinned.env_overrides)["FLYWHEEL_CAPTURE"] == "off"


def test_an_engine_module_launch_keeps_its_cwd_and_still_turns_capture_off(tmp_path):
    launch = LaunchSpec(("python", "-m", "harness.local_mcp"), inherit_env=True)
    pinned = pin_lane_workdir(LANES["local-model"], launch, _parent(tmp_path))
    assert pinned.cwd is None
    assert dict(pinned.env_overrides)["FLYWHEEL_CAPTURE"] == "off"


def test_a_confined_pip_launch_turns_capture_off(tmp_path):
    launch = LaunchSpec(("python", "-I", "-m", "gather.cli", "mcp"), inherit_env=True)
    confined, _codes = confine_lane_launch(LANES["gather"], launch, _parent(tmp_path), {})
    assert dict(confined.env_overrides)["FLYWHEEL_CAPTURE"] == "off"


def test_a_bridge_child_turns_capture_off_even_when_the_call_asks_for_it(tmp_path):
    env = lane_process_environment("index", {"FLYWHEEL_CAPTURE": "on"},
                                   environ=_parent(tmp_path), registry={})
    assert env["FLYWHEEL_CAPTURE"] == "off"


def test_a_granted_name_cannot_turn_capture_back_on(tmp_path):
    registry = {"articulate": {"env_allow": ["FLYWHEEL_CAPTURE"]}}
    env = lane_process_environment("articulate", environ=_parent(tmp_path),
                                   registry=registry)
    assert env["FLYWHEEL_CAPTURE"] == "off"


def test_a_hook_fired_inside_a_lane_child_sends_nothing(tmp_path):
    """End to end: the hook, run with a bridge child's environment while a
    listener waits at the published endpoint, contacts nothing and counts the
    event as suppressed."""
    from harness.capture_hooks import spool
    from harness.gateway_endpoint_file import write_endpoint
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (home / "gateway.token").write_text("synthetic-token-value")
    env = lane_process_environment("articulate", environ=_parent(tmp_path, PYTHONPATH=REPO),
                                   registry={})
    listener = RecordingListener(lambda data: b"{}")
    try:
        write_endpoint(home, "127.0.0.1", listener.port, os.getpid())
        proc = run_hook(home, "stop", stop_event(), cwd=work, env=env)
    finally:
        listener.close()
    assert proc.returncode == 0, proc.stderr.decode()
    assert listener.received == []
    assert spool.suppression_count(home) == 1
    assert spool_files(home) == []


def test_control_the_same_hook_with_capture_on_reaches_the_listener(tmp_path):
    """False-success control: with the engine's environment as it was (capture
    on), the same hook does contact the listener, so the test above can fail."""
    from harness.gateway_endpoint_file import write_endpoint
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (home / "gateway.token").write_text("synthetic-token-value")
    env = _parent(tmp_path, PYTHONPATH=REPO)
    listener = RecordingListener(lambda data: b"{}")
    try:
        write_endpoint(home, "127.0.0.1", listener.port, os.getpid())
        run_hook(home, "stop", stop_event(), cwd=work, env=env)
    finally:
        listener.close()
    assert listener.received != []
