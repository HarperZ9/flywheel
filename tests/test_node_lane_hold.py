"""The Node lane hold, end to end, and the end of the telos hold.

A row with a ``hold`` in packaging/node-lane-payloads.json keeps its lane out of
every freeze and installer, and ``HELD_LANES`` keeps the engine from launching
it. telos carried that hold until 0.4.2 removed the release contents it was
about; its tools are now classified one by one. The mechanism stays for a lane
that needs it again, so these tests hold both in code, not in a hand-edited
manifest copy:

- no committed row holds a lane, and telos stages by default;
- staging skips a held row unless ``include_held`` is passed;
- the freeze refuses a stage receipt that lists a held lane;
- the frozen engine reports a stated hold, not a build defect, for a held lane,
  and looks for Node for telos;
- telos admits its T1 tools, needs Node, and the smoke expects its main action.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_runtime_frozen as lrf
from harness import lane_tool_policy as policy
from harness.lanes import resolve_mcp_command
from harness.lanes_registry import LANES
from scripts.frozen_payload_datas import (FreezeInputError, held_node_lanes,
                                          node_lane_stage_datas)
from scripts.stage_node_lanes import load_manifest, stage_node_lanes
from tests.test_stage_node_lanes import _fixture

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "node-lane-payloads.json"


def _held_fixture(tmp_path):
    manifest, art = _fixture(tmp_path)
    for row in manifest["lanes"]:
        if row["lane"] == "telos":
            row["hold"] = "O-8"
    return manifest, art


def test_no_committed_row_holds_a_lane_and_telos_is_pinned():
    rows = {row["lane"]: row for row in load_manifest(MANIFEST)["lanes"]}
    assert set(rows) == {"learn", "telos"}
    assert not [lane for lane, row in rows.items() if "hold" in row or "hold_reason" in row]
    assert held_node_lanes() == ()
    assert rows["telos"]["version"] == LANES["telos"].version == "0.4.2"


def test_an_unheld_telos_row_stages_by_default_and_the_freeze_takes_it(tmp_path):
    manifest, art = _fixture(tmp_path)
    receipt = stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                               offline=True)
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn", "telos"]
    assert receipt["held"] == []
    stage = tmp_path / "stage"
    assert (stage / "telos" / "demo" / "telos-mcp.mjs").is_file()
    assert node_lane_stage_datas(str(stage)) == [(str(stage.resolve()), "node-lanes")]


def test_staging_skips_a_held_lane_by_default(tmp_path):
    manifest, art = _held_fixture(tmp_path)
    receipt = stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                               offline=True)
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn"]
    assert receipt["held"] == [{"lane": "telos", "hold": "O-8"}]
    stage = tmp_path / "stage"
    assert not (stage / "telos").exists()
    assert not list(stage.rglob("telos-mcp.mjs"))
    # the freeze accepts the stage that left the held lane out
    assert node_lane_stage_datas(str(stage), held=("telos",)) == [
        (str(stage.resolve()), "node-lanes")]


def test_include_held_stages_it_and_the_freeze_refuses_that_stage(tmp_path):
    manifest, art = _held_fixture(tmp_path)
    receipt = stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                               offline=True, include_held=True)
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn", "telos"]
    with pytest.raises(FreezeInputError, match="held"):
        node_lane_stage_datas(str(tmp_path / "stage"), held=("telos",))


def test_the_freeze_reads_the_hold_from_the_manifest_it_is_given(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "node-lane-stage.json").write_text(json.dumps(
        {"verdict": "PASS", "lanes": [{"lane": "learn"}, {"lane": "telos"}]}),
        encoding="utf-8")
    # the committed manifest holds nothing, so the stage passes
    assert node_lane_stage_datas(str(stage)) == [(str(stage.resolve()), "node-lanes")]
    # a manifest that holds telos makes the same stage fail
    held = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for row in held["lanes"]:
        if row["lane"] == "telos":
            row["hold"] = "test-hold"
    path = tmp_path / "held.json"
    path.write_text(json.dumps(held), encoding="utf-8")
    assert held_node_lanes(path) == ("telos",)
    with pytest.raises(FreezeInputError, match="telos"):
        node_lane_stage_datas(str(stage), held=held_node_lanes(path))


def test_the_frozen_engine_states_a_hold_before_looking_for_node(tmp_path, monkeypatch):
    def no_node(*_a, **_k):
        raise AssertionError("a held lane must not look for Node")
    monkeypatch.setitem(policy.HELD_LANES, "telos", "Not in this build.")
    launch, _selected, _component, codes = lrf.select_frozen_launch(
        LANES["telos"], "auto", "engine.exe", {"FLYWHEEL_HOME": str(tmp_path)},
        lambda _m: True, stage_root=tmp_path, find=no_node)
    assert launch is None
    assert codes == ("lane_held",)
    assert lrf.launch_state(codes) == lrf.CANNOT_LAUNCH
    assert lrf.is_blocking("lane_held")


def test_the_frozen_engine_looks_for_node_for_telos_now(tmp_path):
    looked = []

    def find(*_a, **_k):
        looked.append(True)
        raise LookupError("stop here")
    stage = tmp_path / "stage"
    (stage / "telos" / "demo").mkdir(parents=True)
    (stage / "telos" / "demo" / "telos-mcp.mjs").write_text("", encoding="utf-8")
    (stage / "node-lane-stage.json").write_text(json.dumps(
        {"verdict": "PASS", "lanes": [{"lane": "telos"}]}), encoding="utf-8")
    assert policy.HELD_LANES == {}
    with pytest.raises(LookupError):
        lrf.select_frozen_launch(LANES["telos"], "auto", "engine.exe",
                                 {"FLYWHEEL_HOME": str(tmp_path / "home")},
                                 lambda _m: True, stage_root=stage, find=find)
    assert looked == [True]


def test_the_card_says_not_in_this_build_for_a_held_lane(tmp_path, monkeypatch):
    from harness.lane_probe_cache import ProbeCache
    from harness.lane_roster_row import lane_state
    from harness.lane_setup import SetupChecks
    sentence = "Not in this build: a stated hold."
    monkeypatch.setitem(policy.HELD_LANES, "telos", sentence)
    row = {"name": "telos", "status": "missing", "blocking_codes": ["lane_held"]}
    state = lane_state("telos", row, cache=ProbeCache(tmp_path / "c.json"),
                       checks=SetupChecks({"FLYWHEEL_HOME": str(tmp_path)}))
    assert state["state"] == "cannot_launch"
    assert state["code"] == "lane_held"
    assert state["sentence"] == sentence
    assert "Could not start" not in state["sentence"]


def test_telos_admits_its_t1_tools_and_needs_node():
    from harness.lane_setup import lane_needs
    admitted = policy.admitted_tools("telos")
    assert len(admitted) == 37 and "telos.catalog" in admitted
    assert policy.main_tools("telos") == ["telos.catalog", "telos.proof.research",
                                          "telos.proof.visual", "telos.proof.build"]
    assert lane_needs("telos") == ["node"]
    slugs = {e.not_in_build for e in policy.lane_policy("telos").values() if e.not_in_build}
    assert slugs == {"actuation_outside_app"}
    assert "release_on_hold" not in {e.not_in_build for tools in policy.LANE_TOOL_POLICY.values()
                                     for e in tools.values()}
    assert "telos" not in policy.HELD_LANES


def test_the_registry_has_no_distribution_hold_for_telos():
    lane = LANES["telos"]
    assert lane.package_disabled_reason == ""
    assert lane.kind == "npm" and lane.install_name == "project-telos-mcp"
    assert resolve_mcp_command("telos") == ["node", "demo/telos-mcp.mjs"]


def test_the_smoke_row_expects_the_main_action():
    rows = json.loads((ROOT / "packaging" / "lane-smoke-expectations.json").read_text(
        encoding="utf-8"))["lanes"]
    assert rows["telos"] == {"expected": "main", "bar": "A"}
    assert not [lane for lane, row in rows.items() if row.get("reason") == "lane_held"]
