"""The O-8 telos hold, end to end: nothing of telos enters a freeze.

DECISIONS.json holds telos out of every freeze and installer until a contained
release exists and the operator approves it. The staging code path stays, so a
contained release can be pinned later, but it is off by default. These tests
hold that in code, not in a hand-edited manifest copy:

- the committed manifest marks the telos row held;
- staging skips a held row unless ``include_held`` is passed;
- the freeze refuses a stage receipt that lists a held lane;
- the frozen engine reports a stated hold, not a build defect;
- the policy admits no telos tool and the smoke row expects the hold.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_runtime_frozen as lrf
from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES
from scripts.frozen_payload_datas import FreezeInputError, node_lane_stage_datas
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


def test_the_committed_manifest_holds_telos_and_only_telos():
    rows = {row["lane"]: row for row in load_manifest(MANIFEST)["lanes"]}
    assert rows["telos"].get("hold") == "O-8"
    assert "hold" not in rows["learn"]


def test_staging_skips_a_held_lane_by_default(tmp_path):
    manifest, art = _held_fixture(tmp_path)
    receipt = stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                               offline=True)
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn"]
    assert receipt["held"] == [{"lane": "telos", "hold": "O-8"}]
    stage = tmp_path / "stage"
    assert not (stage / "telos").exists()
    assert not list(stage.rglob("telos-mcp.mjs"))
    # the freeze accepts the stage that left telos out
    assert node_lane_stage_datas(str(stage)) == [(str(stage.resolve()), "node-lanes")]


def test_include_held_stages_it_and_the_freeze_refuses_that_stage(tmp_path):
    manifest, art = _held_fixture(tmp_path)
    receipt = stage_node_lanes(tmp_path / "stage", manifest=manifest, artifact_dir=art,
                               offline=True, include_held=True)
    assert [lane["lane"] for lane in receipt["lanes"]] == ["learn", "telos"]
    with pytest.raises(FreezeInputError, match="held"):
        node_lane_stage_datas(str(tmp_path / "stage"), held=("telos",))


def test_the_freeze_reads_the_hold_from_the_committed_manifest(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "node-lane-stage.json").write_text(json.dumps(
        {"verdict": "PASS", "lanes": [{"lane": "learn"}, {"lane": "telos"}]}),
        encoding="utf-8")
    with pytest.raises(FreezeInputError, match="telos"):
        node_lane_stage_datas(str(stage))


def test_the_frozen_engine_states_the_hold_before_looking_for_node(tmp_path):
    def no_node(*_a, **_k):
        raise AssertionError("a held lane must not look for Node")
    launch, _selected, _component, codes = lrf.select_frozen_launch(
        LANES["telos"], "auto", "engine.exe", {"FLYWHEEL_HOME": str(tmp_path)},
        lambda _m: True, stage_root=tmp_path, find=no_node)
    assert launch is None
    assert codes == ("lane_held",)
    assert lrf.launch_state(codes) == lrf.CANNOT_LAUNCH
    assert lrf.is_blocking("lane_held")


def test_the_card_says_not_in_this_build_for_a_held_lane(tmp_path):
    from harness.lane_probe_cache import ProbeCache
    from harness.lane_roster_row import lane_state
    from harness.lane_setup import SetupChecks
    row = {"name": "telos", "status": "missing", "blocking_codes": ["lane_held"]}
    state = lane_state("telos", row, cache=ProbeCache(tmp_path / "c.json"),
                       checks=SetupChecks({"FLYWHEEL_HOME": str(tmp_path)}))
    assert state["state"] == "cannot_launch"
    assert state["code"] == "lane_held"
    assert state["sentence"] == ("Not in this build: Telos is held while its release "
                                 "contents are reviewed.")
    assert "Could not start" not in state["sentence"]


def test_no_telos_tool_is_admitted_and_setup_names_nothing():
    from harness.lane_setup import lane_needs
    assert policy.admitted_tools("telos") == []
    assert policy.main_tools("telos") == []
    assert lane_needs("telos") == []
    reasons = {e.not_in_build for n, e in policy.lane_policy("telos").items()
               if n != "telos.native.control"}
    assert reasons == {"release_on_hold"}
    assert policy.lane_policy("telos")["telos.native.control"].not_in_build
    assert "telos" in policy.HELD_LANES


def test_the_registry_reason_makes_no_shipping_claim():
    reason = LANES["telos"].package_disabled_reason
    assert "ships" not in reason
    assert "holds Telos out" in reason


def test_the_smoke_row_expects_the_hold():
    rows = json.loads((ROOT / "packaging" / "lane-smoke-expectations.json").read_text(
        encoding="utf-8"))["lanes"]
    assert rows["telos"]["expected"] == "cannot_launch"
    assert rows["telos"]["reason"] == "lane_held"
