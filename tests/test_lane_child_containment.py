"""What a spawned lane child can reach: Git on PATH, temp and app-data folders.

POLICY-DECISION C-9 and C-10, security findings S4 and S5, correctness C7:

- the Git folder joins a child's PATH only for a lane whose table lists ``git``
  in some tool's ``needs`` (index), and only a folder holding git from
  ``FLYWHEEL_GIT``, a Git for Windows ``cmd`` folder or Program Files; a shim
  folder found on PATH never joins, since it would expose every tool in it;
- the folder comes from ``tool_discovery.find_git``, the same finder the Git
  setup item reads, so a per-user Git install found through the registry PATH
  reaches the index child too;
- every spawned lane child gets TEMP, TMP, TMPDIR, APPDATA and LOCALAPPDATA
  inside ``<home>/lanes/<lane>/``, and index and accountable-surface write their
  caches, receipts and journal there.
"""
from __future__ import annotations

from pathlib import Path

from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec

_BASE_NT = {"SYSTEMROOT": "C:/Windows", "WINDIR": "C:/Windows", "PATH": "D:/nothing"}


def _exe(folder: Path, name: str = "git.exe") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"")
    return path


def _registry(user: str | None = None, machine: str | None = None):
    return lambda scope: {"user": user, "machine": machine}[scope]


def test_a_per_user_git_found_through_the_registry_path_joins_index(tmp_path):
    from harness.bundled_lane_env import git_directory
    git = _exe(tmp_path / "Programs" / "Git" / "cmd")
    (tmp_path / "Programs" / "Git" / "mingw64").mkdir()
    found = git_directory(_BASE_NT, platform="nt",
                          read_registry_path=_registry(user=str(git.parent)))
    assert found == str(git.parent)


def test_a_shim_folder_on_path_never_joins(tmp_path):
    from harness.bundled_lane_env import git_directory
    shims = tmp_path / "scoop" / "shims"
    _exe(shims)
    _exe(shims, "claude.exe")
    env = {**_BASE_NT, "PATH": str(shims)}
    assert git_directory(env, platform="nt", read_registry_path=_registry()) is None


def test_flywheel_git_and_program_files_are_accepted(tmp_path):
    from harness.bundled_lane_env import git_directory
    pinned = _exe(tmp_path / "anywhere")
    assert git_directory({**_BASE_NT, "FLYWHEEL_GIT": str(pinned)}, platform="nt",
                         read_registry_path=_registry()) == str(pinned.parent)
    assert git_directory({**_BASE_NT, "FLYWHEEL_GIT": "none"}, platform="nt",
                         read_registry_path=_registry()) is None
    program = _exe(tmp_path / "pf" / "Git" / "cmd")
    assert git_directory({**_BASE_NT, "PROGRAMFILES": str(tmp_path / "pf")}, platform="nt",
                         read_registry_path=_registry()) == str(program.parent)


def test_git_joins_only_the_lanes_whose_table_needs_it(tmp_path):
    from harness.bundled_lane_env import bundled_child_environment, lane_needs_git
    assert lane_needs_git("index")
    assert not any(lane_needs_git(lane) for lane in LANES if lane != "index")
    git = str(tmp_path / "Git" / "cmd")
    for lane in ("relay", "forum", None):
        env = bundled_child_environment(_BASE_NT, platform="nt", git_dir=git, lane=lane)
        assert env["PATH"] == "C:/Windows/System32", lane
    env = bundled_child_environment(_BASE_NT, platform="nt", git_dir=git, lane="index")
    assert env["PATH"] == "C:/Windows/System32;" + git


def _home_env(tmp_path: Path) -> dict[str, str]:
    return {"FLYWHEEL_HOME": str(tmp_path / "home"), "TEMP": "D:/user-temp",
            "TMP": "D:/user-temp", "APPDATA": "D:/roaming", "LOCALAPPDATA": "D:/local",
            "PATH": "C:/Windows/System32", "SYSTEMROOT": "C:/Windows"}


def _confined(lane: str, launch: LaunchSpec, environ: dict) -> dict[str, str]:
    from harness.lane_env import confine_lane_launch
    confined, _ = confine_lane_launch(LANES[lane], launch, environ, {})
    return dict(confined.env_overrides)


def test_every_spawned_child_gets_temp_and_app_data_inside_its_lane_folder(tmp_path):
    environ = _home_env(tmp_path)
    pip = LaunchSpec(("python", "-m", "gather", "mcp"), inherit_env=True)
    bundled = LaunchSpec(("D:/app/engine.exe", "--bundled-lane-mcp", "crucible"),
                         env_overrides=tuple(sorted(environ.items())), inherit_env=False)
    for lane, launch in (("gather", pip), ("crucible", bundled)):
        env = _confined(lane, launch, environ)
        folder = (tmp_path / "home").resolve() / "lanes" / lane
        for name in ("TEMP", "TMP", "TMPDIR", "APPDATA", "LOCALAPPDATA"):
            assert Path(env[name]).is_relative_to(folder), (lane, name, env[name])
            assert Path(env[name]).is_dir(), (lane, name)
        assert "D:/user-temp" not in env.values()


def test_index_and_accountable_surface_write_inside_their_lane_folders(tmp_path):
    environ = _home_env(tmp_path)
    home = (tmp_path / "home").resolve()
    index = _confined("index", LaunchSpec(("python", "-m", "index_graph", "mcp"),
                                          inherit_env=True), environ)
    for name in ("INDEX_CACHE_DIR", "INDEX_MCP_CACHE_DIR", "INDEX_GRAPH_REPO_CACHE_DIR"):
        assert Path(index[name]).is_relative_to(home / "lanes" / "index" / "cache"), name
    surface = _confined("accountable-surface", LaunchSpec(
        ("python", "-m", "accountable_surface.interop_mcp"), inherit_env=True), environ)
    folder = home / "lanes" / "accountable-surface"
    assert Path(surface["ACCOUNTABLE_SURFACE_RECEIPTS"]).parent == folder
    assert Path(surface["ACCOUNTABLE_SURFACE_JOURNAL"]).parent == folder


def test_an_operator_set_cache_folder_wins(tmp_path):
    environ = {**_home_env(tmp_path), "INDEX_CACHE_DIR": "D:/my-cache"}
    from harness.lane_env import lane_process_environment
    env = lane_process_environment("index", environ=environ, registry={})
    assert env["INDEX_CACHE_DIR"] == "D:/my-cache"
    assert Path(env["INDEX_MCP_CACHE_DIR"]).is_relative_to(
        (tmp_path / "home").resolve() / "lanes" / "index" / "cache")


def test_relay_always_starts_with_its_grants_off_and_its_root_in_the_lane_folder(tmp_path):
    """relay 0.3.0 reads write, exec and root from its launch; the engine sets
    them, and neither the engine environment nor an env_allow grant wins."""
    from harness.lane_env import confine_lane_launch
    environ = {**_home_env(tmp_path), "RELAY_ALLOW_EXEC": "1", "RELAY_ALLOW_WRITE": "1",
               "RELAY_MCP_ROOT": "C:/"}
    launch = LaunchSpec(("D:/app/engine.exe", "--bundled-lane-mcp", "relay"),
                        env_overrides=(("PATH", "C:/Windows/System32"),), inherit_env=False)
    row = {"env_allow": ["RELAY_ALLOW_EXEC", "RELAY_MCP_ROOT"]}
    confined, _ = confine_lane_launch(LANES["relay"], launch, environ, row)
    env = dict(confined.env_overrides)
    folder = (tmp_path / "home").resolve() / "lanes" / "relay"
    assert (env["RELAY_ALLOW_WRITE"], env["RELAY_ALLOW_EXEC"]) == ("0", "0")
    assert env["RELAY_ALLOW_REMOTE_EXEC"] == "0"
    assert env["RELAY_MCP_ROOT"] == str(folder) == confined.cwd
    pip = LaunchSpec(("relay", "--mcp"), inherit_env=True)
    env = _confined("relay", pip, environ)
    assert (env["RELAY_ALLOW_EXEC"], env["RELAY_MCP_ROOT"]) == ("0", str(folder))

