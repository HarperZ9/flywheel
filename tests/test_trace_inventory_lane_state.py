"""Custody status names every file the lanes layer writes, and where the
pinned mneme keeps its replay snapshots.

Correctness review F2 and F3 of 1.1.0:

- the lane probe cache (``state/lane-probes.json``, written at every
  installed-app start) and the Node choice (``node_path``, written when the
  owner picks a node.exe) showed as UNREGISTERED in ``flywheel traces status``;
  the lanes test only looked under ``lanes/``;
- mneme 0.5.1 keeps full replay copies of the memory database in
  ``<LocalAppData>/mneme/snapshots`` on Windows (through the Known Folder API,
  outside the lane folder) and ``$XDG_STATE_HOME/mneme/snapshots`` or
  ``~/.local/state/mneme/snapshots`` elsewhere. No store counted that folder,
  and the status text said that on Windows it sat in the mneme lane folder.
"""
from __future__ import annotations

import os
import pytest

from harness import trace_inventory as inv
from harness.lane_workdir import ensure_lane_workdir
from harness.lanes_registry import LANES
from harness.trace_inventory_scan import resolve_roots, scan, store_paths


def _home(tmp_path, monkeypatch):
    home, run = tmp_path / "home", tmp_path / "run"
    run.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    return home, {"FLYWHEEL_HOME": str(home)}


def test_the_lanes_layer_leaves_nothing_unregistered_in_any_root(tmp_path, monkeypatch):
    from harness.lane_probe_cache import OUTCOMES, default_cache
    from harness.lane_settings_route import node_executable_name, node_path_post
    home, env = _home(tmp_path, monkeypatch)
    for lane in LANES:
        ensure_lane_workdir(lane, env)
    cache = default_cache(env)
    cache.record("gather", LANES["gather"].version, sorted(OUTCOMES)[0], tools=["gather.docs"])
    cache.record_validated("gather", ["EXAMPLE_KEY"])
    node = tmp_path / "tools" / node_executable_name()
    node.parent.mkdir()
    node.write_bytes(b"node")
    _body, status = node_path_post({"path": str(node)}, env,
                                   version_probe=lambda _p: "v22.0.0")
    assert status == 200 and (home / "node_path").is_file()
    assert (home / "state" / "lane-probes.json").is_file()
    assert scan()["unregistered"] == []


def test_control_an_unknown_file_in_the_home_is_unregistered(tmp_path, monkeypatch):
    home, env = _home(tmp_path, monkeypatch)
    (home / "state").mkdir(parents=True)
    (home / "state" / "not-a-store.json").write_text("{}", encoding="utf-8")
    names = [(r["root"], r["name"]) for r in scan()["unregistered"]]
    assert names == [("state", "not-a-store.json")]


def _snapshot_store():
    rows = [s for s in inv.stores() if s.root == "userstate"]
    assert len(rows) == 1
    return rows[0]


def test_the_snapshot_row_counts_the_folder_mneme_uses_on_posix(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the POSIX folder rule; the Windows rule is checked below")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    folder = tmp_path / "xdg" / "mneme" / "snapshots" / "st_" / "x"
    folder.mkdir(parents=True)
    (folder / "mneme-replay-1-a.db").write_bytes(b"copy")
    row = _snapshot_store()
    assert store_paths(row, resolve_roots()) == [tmp_path / "xdg" / "mneme" / "snapshots"]


def test_the_snapshot_row_reads_the_windows_known_folder(monkeypatch):
    if os.name != "nt":
        pytest.skip("the Windows Known Folder rule")
    from harness.capture_hooks.home import _LOCAL_APPDATA, _known_folder
    from harness.trace_inventory_scan import location_text
    assert resolve_roots()["userstate"] == _known_folder(_LOCAL_APPDATA)
    assert "mneme/snapshots" in location_text(_snapshot_store())


def test_the_status_text_no_longer_puts_the_snapshots_in_the_lane_folder():
    older = next(s for s in inv.stores() if s.id == "L1a")
    assert "sits in the mneme lane folder" not in older.delete.reason
    row = _snapshot_store()
    assert row.classes == ("C1", "C5", "C8")
    assert isinstance(row.delete, inv.Gap)
