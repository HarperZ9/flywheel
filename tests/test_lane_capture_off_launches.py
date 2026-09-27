"""Every lane launch the engine resolves carries capture off.

Correctness review F11 of 1.1.0: the capture-off rule was tested per env
builder, and no committed test resolved each lane's real launch. This one
resolves all 17, frozen and from source, and requires FLYWHEEL_CAPTURE=off on
every launch that spawns a process. In the frozen resolution, where the stage
is forced present, exactly bulletin (a remote board over HTTP) and telos (held
out of the build) spawn nothing, so a lane that silently loses its launch is
seen too.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import harness.lanes as ln
from harness import lane_runtime_frozen as lrf
from harness.lanes_registry import LANES
from tests.test_lane_runtime_frozen import _finder, _pick_root, _stage

NO_PROCESS = {"bulletin", "telos"}


def _capture(name: str) -> str:
    launch = ln.resolve_lane_runtime(name).launch
    if launch is None or not launch.argv or launch.url:
        return "no-launch"
    return dict(launch.env_overrides).get("FLYWHEEL_CAPTURE", "missing")


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    home = Path(ln.os.environ["FLYWHEEL_HOME"])
    stage = _stage(tmp_path)
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    monkeypatch.setattr(ln, "_importable", lambda top: True)
    monkeypatch.setattr(lrf, "_stage_root", lambda: stage)
    monkeypatch.setattr(lrf, "find_node", _finder())
    project = tmp_path / "project"
    project.mkdir()
    _pick_root(home, project)


def test_every_frozen_lane_launch_has_capture_off(frozen):
    seen = {name: _capture(name) for name in LANES}
    assert {n for n, v in seen.items() if v == "no-launch"} == NO_PROCESS, seen
    assert {n: v for n, v in seen.items() if v not in ("off", "no-launch")} == {}


def test_every_source_lane_launch_that_resolves_has_capture_off():
    seen = {}
    for name in LANES:
        try:
            seen[name] = _capture(name)
        except Exception as exc:     # a lane this host cannot resolve spawns nothing
            seen[name] = f"unresolved: {type(exc).__name__}"
    assert {n: v for n, v in seen.items()
            if v not in ("off", "no-launch") and not v.startswith("unresolved")} == {}
