"""Every lane folder the lanes layer creates is a registered custody store.

The lanes layer starts each lane child in `<home>/lanes/<lane>` and points its
temp and app-data folders there (harness/lane_workdir.py). Trace custody lists
every entry under `lanes/` that no store claims as UNREGISTERED, so a lane
without a row would show up as unknown data in `flywheel traces status`.
"""
from __future__ import annotations

import pytest

from harness import trace_inventory as inv
from harness.lane_workdir import ensure_lane_workdir
from harness.lanes_registry import LANES
from harness.trace_inventory_scan import scan


@pytest.mark.parametrize("lane", sorted(LANES))
def test_every_registered_lane_folder_is_a_store(lane):
    found = inv.classify("lanes", lane)
    assert isinstance(found, inv.Store), lane
    assert found.owner_binding == "lane"


def test_each_lane_folder_has_exactly_one_row():
    for lane in LANES:
        rows = [s.id for s in inv.stores()
                if s.root == "lanes" and lane in s.patterns]
        assert len(rows) == 1, (lane, rows)


def test_relay_folder_names_its_saved_sessions():
    relay = inv.classify("lanes", "relay")
    assert relay.classes == ("C1", "C2")
    assert "saved sessions" in relay.note


def test_lane_folders_the_engine_creates_are_not_unregistered(tmp_path, monkeypatch):
    home, run = tmp_path / "home", tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    for lane in LANES:
        ensure_lane_workdir(lane, {"FLYWHEEL_HOME": str(home)})
    unregistered = [row for row in scan()["unregistered"] if row["root"] == "lanes"]
    assert unregistered == []


def test_control_a_folder_no_lane_owns_is_unregistered(tmp_path, monkeypatch):
    """False-success control: the scan does report a lanes/ entry nobody claims."""
    home, run = tmp_path / "home", tmp_path / "run"
    run.mkdir()
    (home / "lanes" / "not-a-lane").mkdir(parents=True)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    names = [row["name"] for row in scan()["unregistered"] if row["root"] == "lanes"]
    assert names == ["not-a-lane"]
