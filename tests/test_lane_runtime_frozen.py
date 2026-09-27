"""Frozen lane launches: no bare interpreter, no bare node, no console script.

The installed app's engine is a frozen executable on a clean machine, so a
declared ``python -m ...``, ``node <script>`` or ``<command> mcp`` argv cannot
start there. Every frozen launch must be the engine itself in a vetted child
mode, an absolute Node on a staged script, or an http endpoint. A lane that
cannot launch names a code, and a code the person can fix names a setup item.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import harness.lanes as ln
from harness import lane_runtime_frozen as lrf
from harness import tool_discovery as td
from harness.lane_runtime import LaneRuntimeError
from harness.lane_tool_policy import admitted_tools
from harness.lanes_registry import LANES, Lane

_NODE_ENTRIES = (("learn", "src/mcp.mjs"), ("telos", "demo/telos-mcp.mjs"))


def _stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage" / "node-lanes"
    (stage / "node").mkdir(parents=True)
    (stage / "node" / "node.exe").write_bytes(b"")
    for lane, entry in _NODE_ENTRIES:
        script = stage / lane / entry
        script.parent.mkdir(parents=True)
        script.write_text("// entry\n", encoding="utf-8")
    receipt = {"verdict": "PASS", "lanes": [{"lane": name} for name, _ in _NODE_ENTRIES]}
    (stage / "node-lane-stage.json").write_text(json.dumps(receipt), encoding="utf-8")
    return stage


def _finder(version: str | None = "v24.21.0"):
    def find(environ, *, bundled=None):
        return td.find_node(environ, bundled=bundled, platform="nt",
                            read_registry_path=lambda scope: None,
                            node_version=lambda path: version)
    return find


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    """A frozen engine with a staged Node lane folder and a throwaway home."""
    home = Path(ln.os.environ["FLYWHEEL_HOME"])
    stage = _stage(tmp_path)
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setattr(lrf, "_stage_root", lambda: stage)
    monkeypatch.setattr(lrf, "find_node", _finder())
    return {"home": home, "stage": stage, "tmp": tmp_path}


def _pick_root(home: Path, folder: Path | str) -> None:
    target = home / "lanes" / "local-model"
    target.mkdir(parents=True, exist_ok=True)
    (target / "root").write_text(str(folder) + "\n", encoding="utf-8")


def _console_scripts() -> set[str]:
    return {lane.command for lane in LANES.values()
            if lane.command and lane.command not in {"python", "node"}}


def test_no_frozen_argv_starts_with_python_node_or_a_console_script(frozen):
    project = frozen["tmp"] / "project"
    project.mkdir()
    _pick_root(frozen["home"], project)
    bare = {"python", "python3", "python.exe", "node", "node.exe", *_console_scripts()}
    launched = []
    for name in LANES:
        runtime = ln.resolve_lane_runtime(name)
        launch = runtime.launch
        if launch is None or not launch.argv:
            assert LANES[name].kind == "http" or runtime.blocking_codes, name
            continue
        head = launch.argv[0]
        assert head not in bare, f"{name} launches a bare {head!r}"
        assert Path(head).is_absolute(), f"{name} launches a relative {head!r}"
        # the frozen exe refuses -m (gateway_entry), so no argv may carry it (C15),
        # and the head is the engine itself or the staged node
        assert launch.argv[1:2] != ("-m",), f"{name} launches -m"
        staged_node = str(frozen["stage"] / "node" / "node.exe")
        assert head in (ln.sys.executable, staged_node), f"{name} launches {head!r}"
        launched.append(name)
    assert {"learn", "local-model", "writing", "gather"} <= set(launched)
    assert "telos" not in launched  # held (O-8): no launch, a stated hold code


def test_frozen_learn_runs_the_staged_script_on_the_bundled_node_and_telos_is_held(frozen):
    runtime = ln.resolve_lane_runtime("telos")
    assert runtime.launch is None and runtime.blocking_codes == ("lane_held",)
    for name, entry in _NODE_ENTRIES[:1]:
        launch = ln.resolve_mcp_launch(name)
        assert launch.argv == (str(frozen["stage"] / "node" / "node.exe"),
                               str((frozen["stage"] / name / entry).resolve()))
        assert launch.allowed_tools == tuple(admitted_tools(name)), name
        assert launch.inherit_env is False, name
        assert Path(launch.cwd) == frozen["home"] / "lanes" / name


def test_frozen_node_lane_without_node_needs_setup(frozen, monkeypatch):
    monkeypatch.setattr(lrf, "find_node", _finder(version=None))
    monkeypatch.setenv("FLYWHEEL_NODE", "none")
    runtime = ln.resolve_lane_runtime("learn")
    assert runtime.launch is None
    assert "node_runtime_missing" in runtime.blocking_codes
    assert lrf.setup_items(runtime.blocking_codes) == ("node",)
    assert lrf.launch_state(runtime.blocking_codes) == lrf.NEEDS_SETUP


def test_frozen_node_lane_without_its_stage_cannot_launch(frozen, monkeypatch):
    monkeypatch.setattr(lrf, "_stage_root", lambda: None)
    runtime = ln.resolve_lane_runtime("learn")
    assert runtime.blocking_codes == ("node_lane_not_staged",)
    assert lrf.launch_state(runtime.blocking_codes) == lrf.CANNOT_LAUNCH


def test_local_model_runs_the_engine_mcp_mode_on_the_picked_folder(frozen):
    project = frozen["tmp"] / "project"
    project.mkdir()
    _pick_root(frozen["home"], project)
    launch = ln.resolve_mcp_launch("local-model")
    assert launch.argv == (sys.executable, "--mcp", "--root", str(project.resolve()))
    assert launch.hide_window is True
    assert Path(launch.cwd) == frozen["home"] / "lanes" / "local-model"


def test_local_model_without_a_folder_needs_setup(frozen):
    runtime = ln.resolve_lane_runtime("local-model")
    assert runtime.blocking_codes == ("local_model_root_unset",)
    assert lrf.setup_items(runtime.blocking_codes) == ("project_folder",)
    assert lrf.launch_state(runtime.blocking_codes) == lrf.NEEDS_SETUP
    with pytest.raises(LaneRuntimeError):
        runtime.require_launch()


@pytest.mark.parametrize("where", ["home", "inside_home", "missing"])
def test_local_model_folder_inside_flywheel_home_or_missing_needs_setup(frozen, where):
    home = frozen["home"]
    folder = {"home": home, "inside_home": home / "projects" / "p",
              "missing": frozen["tmp"] / "not-there"}[where]
    if where == "inside_home":
        folder.mkdir(parents=True)
    _pick_root(home, folder)
    runtime = ln.resolve_lane_runtime("local-model")
    expected = "local_model_root_missing" if where == "missing" else "local_model_root_protected"
    assert runtime.blocking_codes == (expected,)
    assert lrf.launch_state(runtime.blocking_codes) == lrf.NEEDS_SETUP


def test_local_model_folder_holding_the_flywheel_home_needs_setup(frozen):
    _pick_root(frozen["home"], frozen["home"].parent)
    runtime = ln.resolve_lane_runtime("local-model")
    assert runtime.blocking_codes == ("local_model_root_protected",)


def test_writing_runs_the_engine_lane_mcp_mode(frozen):
    launch = ln.resolve_mcp_launch("writing")
    assert launch.argv == (sys.executable, "--lane-mcp", "writing")
    assert Path(launch.cwd) == frozen["home"] / "lanes" / "writing"


def test_a_pip_lane_without_a_payload_is_not_in_this_build(frozen, monkeypatch):
    lane = Lane("zz-probe", "zz-probe", "zz-probe", ("mcp",), "pip", "0.1.0",
                "probe", "test", py_module="zz_probe.cli")
    monkeypatch.setattr(ln, "LANES", {**LANES, "zz-probe": lane})
    runtime = ln.resolve_lane_runtime("zz-probe")
    assert runtime.launch is None
    assert runtime.blocking_codes == ("frozen_lane_not_in_build",)
    assert lrf.launch_state(runtime.blocking_codes) == lrf.CANNOT_LAUNCH


def test_payload_and_http_lanes_keep_their_frozen_launches(frozen):
    gather = ln.resolve_mcp_launch("gather")
    assert gather.argv == (sys.executable, "--bundled-lane-mcp", "gather")
    bulletin = ln.resolve_lane_runtime("bulletin")
    assert bulletin.launch.argv == () and bulletin.launch.url
    assert not bulletin.blocking_codes


def test_states_and_setup_items_from_codes():
    assert lrf.launch_state(()) is None
    assert lrf.launch_state(("source_version_mismatch",)) is None
    assert lrf.launch_state(("bundled_module_missing",)) == lrf.CANNOT_LAUNCH
    assert lrf.launch_state(("node_runtime_too_old", "local_model_root_unset")) == lrf.NEEDS_SETUP
    assert lrf.setup_items(("node_runtime_missing", "node_runtime_too_old")) == ("node",)


def test_registry_fixes_ride_with_the_launch_paths():
    assert LANES["chorus"].py_module == "chorus"  # chorus.cli has no main guard
    assert LANES["canon"].py_module == "canon"    # PyPI canon.cli has no main guard
    assert LANES["bulletin"].version == "0.5.0"   # what the live board reports
    assert LANES["telos"].version == "0.4.1"      # the held GitHub release (O-8 hold)


def test_pip_chorus_and_canon_launch_through_their_package_main(monkeypatch):
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: lane.version)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    for name in ("chorus", "canon"):
        launch = ln.resolve_mcp_launch(name)
        assert launch.argv == (sys.executable, "-m", name, "mcp"), name
