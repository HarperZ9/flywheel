"""Every spawned lane child starts in its own folder under the Flywheel home.

A lane that writes relative to its working directory (forum's ledger, mneme's
database, learn and telos state) used to write wherever the engine happened to
start, which for an all-users install is the Program Files folder. These tests
pin the folder, the state defaults that live in it, and the launches that get it.
"""
from pathlib import Path

import pytest

from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec


def _home(tmp_path):
    home = tmp_path / "fw-home"
    return home, {"FLYWHEEL_HOME": str(home)}


def test_workdir_sits_under_home_lanes_and_is_created(tmp_path):
    from harness.lane_workdir import ensure_lane_workdir, lane_workdir

    home, env = _home(tmp_path)
    expected = home.resolve() / "lanes" / "forum"
    assert lane_workdir("forum", env) == expected
    assert not expected.exists()
    assert ensure_lane_workdir("forum", env) == expected
    assert expected.is_dir()


def test_workdir_defaults_to_user_flywheel_folder(monkeypatch, tmp_path):
    from harness.lane_workdir import lane_workdir

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert lane_workdir("gather", {}) == (
        Path(tmp_path).resolve() / ".flywheel" / "lanes" / "gather")


@pytest.mark.parametrize("name", ["", "../x", "a/b", "A", "x" * 80, "..", "c:"])
def test_unsafe_lane_name_is_refused(tmp_path, name):
    from harness.lane_workdir import lane_workdir

    with pytest.raises(ValueError):
        lane_workdir(name, _home(tmp_path)[1])


def test_canon_blocks_folder_is_created_and_named(tmp_path):
    from harness.lane_workdir import ensure_lane_workdir, lane_state_defaults

    home, env = _home(tmp_path)
    folder = ensure_lane_workdir("canon", env)
    blocks = folder / "blocks"
    assert blocks.is_dir()
    assert lane_state_defaults("canon", folder, env) == {
        "CANON_BLOCKS_DIR": str(blocks)}


def test_mneme_state_defaults_into_the_lane_folder(tmp_path):
    from harness.lane_workdir import ensure_lane_workdir, lane_state_defaults

    folder = ensure_lane_workdir("mneme", _home(tmp_path)[1])
    assert lane_state_defaults("mneme", folder, {}) == {
        "MNEME_STATE": str(folder / "mneme.db")}


def test_user_set_state_variable_wins(tmp_path):
    from harness.lane_workdir import lane_state_defaults

    folder = tmp_path / "lanes" / "mneme"
    assert lane_state_defaults("mneme", folder, {"MNEME_STATE": "D:/mine.db"}) == {}
    assert lane_state_defaults("mneme", folder, {"mneme_state": "D:/mine.db"}) == {}
    assert lane_state_defaults("gather", folder, {}) == {}


def test_pin_sets_cwd_for_a_package_launch_and_adds_state(tmp_path):
    from harness.lane_workdir import pin_lane_workdir

    home, env = _home(tmp_path)
    launch = LaunchSpec(("python", "-I", "-m", "mneme.cli", "mcp"),
                        env_overrides=(("PATH", "x"),), inherit_env=False)
    pinned = pin_lane_workdir(LANES["mneme"], launch, env)
    folder = home.resolve() / "lanes" / "mneme"
    assert pinned.cwd == str(folder)
    assert folder.is_dir()
    assert dict(pinned.env_overrides)["MNEME_STATE"] == str(folder / "mneme.db")
    assert dict(pinned.env_overrides)["PATH"] == "x"


def test_pin_keeps_an_explicit_cwd(tmp_path):
    from harness.lane_workdir import pin_lane_workdir

    source = str(tmp_path / "src")
    launch = LaunchSpec(("python", "-m", "gather.cli", "mcp"), source,
                        (("PYTHONPATH", "p"),), False)
    pinned = pin_lane_workdir(LANES["gather"], launch, _home(tmp_path)[1])
    assert pinned.cwd == source
    assert dict(pinned.env_overrides)["GATHER_ALLOW_NETWORK"] == ""


def test_pin_leaves_http_alone_and_engine_self_modules_their_cwd(tmp_path):
    from harness.lane_workdir import pin_lane_workdir

    env = _home(tmp_path)[1]
    http = LaunchSpec((), url="https://example.invalid/mcp")
    assert pin_lane_workdir(LANES["bulletin"], http, env) is http
    self_module = LaunchSpec(("python", "-m", "harness.local_mcp"))
    pinned = pin_lane_workdir(LANES["local-model"], self_module, env)
    assert pinned.cwd is None and pinned.argv == self_module.argv
    assert "TEMP" in dict(pinned.env_overrides)


def test_inheriting_launch_gets_state_as_overrides_only_when_unset(tmp_path):
    from harness.lane_workdir import pin_lane_workdir

    env = {**_home(tmp_path)[1], "MNEME_STATE": "D:/mine.db"}
    launch = LaunchSpec(("mneme", "mcp"))
    pinned = pin_lane_workdir(LANES["mneme"], launch, env)
    assert pinned.inherit_env is True
    assert "MNEME_STATE" not in dict(pinned.env_overrides)


def test_resolved_package_launch_runs_in_lane_folder_not_engine_cwd(
        tmp_path, monkeypatch):
    """F-6: the engine's own working directory (an install folder) stays clean."""
    import harness.lanes as lanes

    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.chdir(install)
    home = Path(tmp_path / "home")
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_importable", lambda name: True)
    monkeypatch.setattr(lanes, "_installed_version",
                        lambda lane: lane.version)
    launch = lanes.resolve_mcp_launch("mneme")
    folder = home.resolve() / "lanes" / "mneme"
    assert launch.cwd == str(folder)
    assert dict(launch.env_overrides)["MNEME_STATE"] == str(folder / "mneme.db")
    assert list(install.iterdir()) == []


def test_bridge_children_share_the_lane_state_defaults(tmp_path):
    """The canon context child and the canon lane read one blocks folder."""
    from harness.lane_env import lane_process_environment

    home, env = _home(tmp_path)
    blocks = home.resolve() / "lanes" / "canon" / "blocks"
    child = lane_process_environment("canon", environ=env, registry={})
    assert child["CANON_BLOCKS_DIR"] == str(blocks) and blocks.is_dir()
    mine = lane_process_environment("canon", {"CANON_BLOCKS_DIR": "D:/b"},
                                    environ=env, registry={})
    assert mine["CANON_BLOCKS_DIR"] == "D:/b"
    assert "MNEME_STATE" not in lane_process_environment(
        "gather", environ=env, registry={})
