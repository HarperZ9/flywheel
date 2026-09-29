"""A source-checkout lane starts in its lane folder with the forced grants.

A source launch used to name its checkout as cwd, and ``pin_lane_workdir``
returned early for any launch with a cwd. So on a source install:

- the path guard resolved a relative argument from ``<home>/lanes/<lane>``
  while the child resolved it from the checkout, and
  ``..\\..\\..\\Users\\me\\.flywheel\\state\\secret.json`` passed the guard;
- relay's and gather's forced launch grants were not applied, so an env_allow of
  ``GATHER_ALLOW_NETWORK`` or ``RELAY_ALLOW_EXEC`` reached the child;
- TEMP and app data were not scoped to the lane folder.

The import root travels in PYTHONPATH with PYTHONSAFEPATH=1, so the checkout
does not need to be the cwd. Every spawned lane child now gets the forced env
and scoped folders; a launch that names its own cwd keeps it, and the engine's
own ``harness.*`` modules keep the engine's import root. A ``python -m`` lane
started in its lane folder gets PYTHONSAFEPATH=1, so a ``relay.py`` left in
that folder cannot shadow the package.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import harness.lanes as ln
from harness.lane_workdir import pin_lane_workdir
from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    monkeypatch.setenv("FLYWHEEL_HOME", str(root))
    return root.resolve()


def _source(tmp_path, top: str, module: str) -> Path:
    source = tmp_path / "public" / top
    package = source / "src" / top
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / f"{module}.py").write_text("", encoding="utf-8")
    return source


def _registry(monkeypatch, tmp_path, rows):
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", path)


def test_a_source_gather_launch_starts_in_its_lane_folder_with_no_grant(
        tmp_path, monkeypatch, home):
    source = _source(tmp_path, "gather", "cli")
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    monkeypatch.setenv("GATHER_ALLOW_NETWORK", "all")
    _registry(monkeypatch, tmp_path, {"gather": {"env_allow": ["GATHER_ALLOW_NETWORK"]}})
    launch = ln.resolve_mcp_launch("gather")
    folder = home / "lanes" / "gather"
    env = dict(launch.env_overrides)
    assert launch.cwd == str(folder)
    assert env["GATHER_ALLOW_NETWORK"] == ""
    assert Path(env["TEMP"]).parent == folder
    assert env["PYTHONSAFEPATH"] == "1"
    assert str((source / "src").resolve()) in env["PYTHONPATH"].split(os.pathsep)
    child = {**os.environ, **env}
    result = subprocess.run(
        [launch.argv[0], "-c", "import gather.cli; print(gather.cli.__file__)"],
        cwd=launch.cwd, env=child, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (
        source / "src" / "gather" / "cli.py").resolve()


def test_a_source_relay_launch_gets_write_and_exec_off(tmp_path, monkeypatch, home):
    source = _source(tmp_path, "relay", "__main__")
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    monkeypatch.setenv("RELAY_ALLOW_EXEC", "1")
    _registry(monkeypatch, tmp_path, {"relay": {"env_allow": ["RELAY_ALLOW_EXEC"]}})
    launch = ln.resolve_mcp_launch("relay")
    env = dict(launch.env_overrides)
    assert (env["RELAY_ALLOW_WRITE"], env["RELAY_ALLOW_EXEC"]) == ("0", "0")
    assert env["RELAY_MCP_ROOT"] == str(home / "lanes" / "relay") == launch.cwd


def test_the_guard_resolves_from_the_folder_the_child_starts_in(
        tmp_path, monkeypatch, home):
    from harness.lane_tier_gate import argument_refusal
    source = _source(tmp_path, "gather", "cli")
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    _registry(monkeypatch, tmp_path, {})
    (home / "state").mkdir(parents=True)
    (home / "state" / "secret.json").write_text("{}", encoding="utf-8")
    launch = ln.resolve_mcp_launch("gather")
    assert Path(launch.cwd) == home / "lanes" / "gather"
    relative = os.path.relpath(home / "state" / "secret.json", launch.cwd)
    assert argument_refusal("gather", "gather.docs", {"path": relative})


def test_a_pip_python_launch_cannot_be_shadowed_from_its_lane_folder(home):
    launch = LaunchSpec((sys.executable, "-m", "relay", "--mcp"))
    pinned = pin_lane_workdir(LANES["relay"], launch, {"FLYWHEEL_HOME": str(home)})
    assert dict(pinned.env_overrides)["PYTHONSAFEPATH"] == "1"


def test_an_explicit_cwd_is_kept_but_the_grants_are_forced(tmp_path, home):
    launch = LaunchSpec(("python", "-m", "gather.cli", "mcp"), str(tmp_path / "work"),
                        (("GATHER_ALLOW_EXEC", "python"),), False)
    pinned = pin_lane_workdir(LANES["gather"], launch, {"FLYWHEEL_HOME": str(home)})
    env = dict(pinned.env_overrides)
    assert pinned.cwd == str(tmp_path / "work")
    assert env["GATHER_ALLOW_EXEC"] == ""
    assert Path(env["TEMP"]).parent == home / "lanes" / "gather"


def test_an_engine_module_keeps_its_import_root_and_gets_scoped_folders(home):
    launch = LaunchSpec(("python", "-m", "harness.local_mcp"))
    pinned = pin_lane_workdir(LANES["local-model"], launch, {"FLYWHEEL_HOME": str(home)})
    env = dict(pinned.env_overrides)
    assert pinned.cwd is None
    assert "PYTHONSAFEPATH" not in env
    assert Path(env["LOCALAPPDATA"]).is_relative_to(home / "lanes" / "local-model")
