"""Node lane launches: an absolute node, an absolute script, the lane folder as cwd.

learn and telos used to launch as ``node src/mcp.mjs``: a bare ``node`` that a
frozen child's System32 PATH cannot find, and a script path relative to the
engine's working directory. The resolver names both absolutely for the frozen
stage, an npm global install and a source checkout, and states the Node setup
item when no usable Node exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness import node_lanes as nl
from harness import tool_discovery as td
from harness.lane_tool_policy import admitted_tools, lane_policy, main_tools, validate_policy
from harness.lanes_registry import LANES

REPO = Path(__file__).resolve().parents[1]
PINS = {row["lane"]: row for row in json.loads(
    (REPO / "packaging" / "node-lane-payloads.json").read_text(encoding="utf-8"))["lanes"]}


def _stage(tmp_path: Path, verdict: str = "PASS") -> Path:
    stage = tmp_path / "node-lanes"
    (stage / "node").mkdir(parents=True)
    (stage / "node" / "node.exe").write_bytes(b"")
    for lane, entry in (("learn", "src/mcp.mjs"), ("telos", "demo/telos-mcp.mjs")):
        script = stage / lane / entry
        script.parent.mkdir(parents=True)
        script.write_text("// entry\n", encoding="utf-8")
    receipt = {"verdict": verdict, "lanes": [{"lane": "learn", "version": "1.6.0"},
                                             {"lane": "telos", "version": "0.4.1"}]}
    (stage / "node-lane-stage.json").write_text(json.dumps(receipt), encoding="utf-8")
    return stage


def _finder(version: str | None = "v24.21.0"):
    def find(environ, *, bundled=None):
        return td.find_node(environ, bundled=bundled, platform="nt",
                            read_registry_path=lambda scope: None,
                            node_version=lambda path: version)
    return find


def _env(tmp_path, **extra):
    return {"FLYWHEEL_HOME": str(tmp_path / "home"), "PATH": "", **extra}


def test_frozen_learn_launches_the_bundled_node_on_an_absolute_script(tmp_path):
    stage = _stage(tmp_path)
    res = nl.resolve_node_lane(LANES["learn"], "frozen", _env(tmp_path),
                               stage_root=stage, find=_finder())
    assert res.codes == () and res.setup == ()
    assert res.launch.argv == (str(stage / "node" / "node.exe"),
                               str(stage / "learn" / "src" / "mcp.mjs"))
    assert all(Path(arg).is_absolute() for arg in res.launch.argv)
    folder = tmp_path / "home" / "lanes" / "learn"
    assert res.launch.cwd == str(folder) and folder.is_dir()
    assert res.node.source == "bundled"
    assert res.launch.hide_window is True


def test_frozen_launch_carries_the_policy_t1_tools_only(tmp_path):
    stage = _stage(tmp_path)
    res = nl.resolve_node_lane(LANES["learn"], "frozen", _env(tmp_path),
                               stage_root=stage, find=_finder())
    assert res.launch.allowed_tools == tuple(admitted_tools("learn"))
    assert "learn_tutor_plan" in res.launch.allowed_tools
    assert "learn_tutor_record" not in res.launch.allowed_tools  # T2
    # telos is held (O-8): its launch, if one were built, would admit nothing
    held = nl.resolve_node_lane(LANES["telos"], "frozen", _env(tmp_path),
                                stage_root=stage, find=_finder())
    assert held.launch.allowed_tools == ()


def test_no_node_gives_the_node_setup_item_and_no_launch(tmp_path):
    res = nl.resolve_node_lane(LANES["learn"], "frozen", _env(tmp_path, FLYWHEEL_NODE="none"),
                               stage_root=_stage(tmp_path), find=_finder())
    assert res.launch is None
    assert res.codes == ("node_runtime_missing",) and res.setup == ("node",)
    assert res.node.source == "disabled"


def test_an_old_node_is_a_setup_item_too(tmp_path):
    old = tmp_path / "old" / "node.exe"
    old.parent.mkdir()
    old.write_bytes(b"")
    res = nl.resolve_node_lane(LANES["telos"], "frozen", _env(tmp_path, FLYWHEEL_NODE=str(old)),
                               stage_root=_stage(tmp_path), find=_finder("v18.19.0"))
    assert res.launch is None
    assert res.codes == ("node_runtime_too_old",) and res.setup == ("node",)


@pytest.mark.parametrize("verdict", ["FAIL", "STAGING"])
def test_a_stage_without_a_passing_receipt_is_not_staged(tmp_path, verdict):
    res = nl.resolve_node_lane(LANES["learn"], "frozen", _env(tmp_path),
                               stage_root=_stage(tmp_path, verdict), find=_finder())
    assert res.launch is None and res.codes == ("node_lane_not_staged",)


def test_a_missing_stage_is_not_staged(tmp_path):
    res = nl.resolve_node_lane(LANES["learn"], "frozen", _env(tmp_path),
                               stage_root=tmp_path / "absent", find=_finder())
    assert res.codes[0] == "node_lane_not_staged"


def test_package_mode_uses_the_npm_global_root(tmp_path):
    root = tmp_path / "npm-root"
    script = root / "@harperz9" / "learn" / "src" / "mcp.mjs"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    node = tmp_path / "nodejs" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"")
    res = nl.resolve_node_lane(LANES["learn"], "package", _env(tmp_path, FLYWHEEL_NODE=str(node)),
                               package_root=root, find=_finder())
    assert res.launch.argv == (str(node), str(script))
    assert res.launch.cwd == str(tmp_path / "home" / "lanes" / "learn")


def test_source_mode_uses_the_checkout_entry(tmp_path):
    source = tmp_path / "telos"
    script = source / "demo" / "telos-mcp.mjs"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    node = tmp_path / "node.exe"
    node.write_bytes(b"")
    res = nl.resolve_node_lane(LANES["telos"], "source", _env(tmp_path, FLYWHEEL_NODE=str(node)),
                               source=source, find=_finder())
    assert res.launch.argv == (str(node), str(script.resolve()))


def test_a_missing_script_is_named(tmp_path):
    node = tmp_path / "node.exe"
    node.write_bytes(b"")
    res = nl.resolve_node_lane(LANES["telos"], "source", _env(tmp_path, FLYWHEEL_NODE=str(node)),
                               source=tmp_path / "empty", find=_finder())
    assert res.launch is None and res.codes == ("node_lane_script_missing",)


def test_no_launch_ever_starts_with_a_bare_node(tmp_path):
    stage = _stage(tmp_path)
    for name in nl.NODE_LANES:
        res = nl.resolve_node_lane(LANES[name], "frozen", _env(tmp_path),
                                   stage_root=stage, find=_finder())
        assert res.launch.argv[0] not in ("node", "node.exe")


def test_only_npm_lanes_resolve_here(tmp_path):
    with pytest.raises(ValueError, match="not a Node lane"):
        nl.resolve_node_lane(LANES["gather"], "frozen", _env(tmp_path), find=_finder())
    with pytest.raises(ValueError, match="mode"):
        nl.resolve_node_lane(LANES["learn"], "sideways", _env(tmp_path), find=_finder())


def test_frozen_stage_root_is_node_lanes_under_meipass(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert nl.frozen_stage_root() == tmp_path / "node-lanes"
    monkeypatch.setattr(sys, "frozen", False)
    assert nl.frozen_stage_root() is None


def test_resolution_serializes_without_the_environment(tmp_path):
    res = nl.resolve_node_lane(LANES["learn"], "frozen",
                               _env(tmp_path, SOME_API_KEY="sk-planted-fake-value"),
                               stage_root=_stage(tmp_path), find=_finder())
    text = json.dumps(res.to_dict())
    assert "sk-planted-fake-value" not in text and res.to_dict()["codes"] == []


@pytest.mark.parametrize("lane", ["learn", "telos"])
def test_policy_covers_exactly_the_pinned_tool_names(lane):
    assert validate_policy() == []
    assert set(lane_policy(lane)) == set(PINS[lane]["static_tool_names"])
    for name in admitted_tools(lane):
        assert name in PINS[lane]["static_tool_names"]


def test_policy_draft_for_the_node_lanes():
    telos = lane_policy("telos")
    assert main_tools("telos") == []
    assert telos["telos.native.control"].not_in_build == "actuation_outside_app"
    assert telos["telos.room"].not_in_build == "release_on_hold"
    assert admitted_tools("telos") == []
    assert main_tools("learn") == ["learn_dry_run", "learn_tutor_plan"]
    assert lane_policy("learn")["learn_tutor_record"].tier == "T2"
    assert "learn_tutor_record" not in admitted_tools("learn")
