"""Held lanes stay at no_frozen_launch in the frozen smoke, whatever the host has.

Empty plans go through ``run_lane_smoke`` as test_frozen_gateway_lane_smoke
does, while the host carries a source folder at each registry pointer under a
scratch FLYWHEEL_WORKSPACE_ROOT and a stray descriptor under a scratch
FLYWHEEL_HOME. The frozen selection and the payload admission are checked under
the same host. The last test pins the registry pointers the source route uses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness import lane_runtime
from harness import lane_runtime_frozen as lrf
from harness.bundled_lane_admission import admit_bundled_lane
from harness.bundled_lane_descriptor import load_manifest_rows
from harness.lane_runtime_support import resolve_source_repo
from harness.lane_tool_policy import HELD_LANES
from harness.lanes_registry import LANES
from scripts import frozen_gateway_lane_smoke as smoke
from scripts.frozen_lane_smoke_plans import HEALTH_TOOLS

HELD = tuple(sorted(HELD_LANES))
REPO = Path(__file__).resolve().parents[1]


def _plant_sources(root: Path) -> dict[str, Path]:
    """A folder at each registry pointer with a stand-in top package."""
    planted = {}
    for name in HELD:
        lane = LANES[name]
        folder = root / Path(lane.source_repo)
        top = lane.py_module.split(".")[0]
        (folder / top).mkdir(parents=True)
        (folder / top / "__init__.py").write_text("", encoding="utf-8")
        (folder / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "{lane.version}"\n', encoding="utf-8")
        planted[name] = folder
    return planted


def _plant_descriptors(home: Path) -> dict[str, Path]:
    """A stray descriptor per held lane plus a registry file under the home."""
    folder = home / "lanes.d"
    folder.mkdir(parents=True)
    paths = {}
    for name in HELD:
        lane = LANES[name]
        paths[name] = folder / f"{name}.json"
        paths[name].write_text(json.dumps({
            "lane": name, "module": lane.py_module, "version": lane.version,
            "allowed_tools": [f"{name}.status"]}), encoding="utf-8")
    (home / "lanes.json").write_text(json.dumps({
        name: {"kind": "pip", "profile": "source", "installed": True,
               "version": LANES[name].version} for name in HELD}), encoding="utf-8")
    return paths


@pytest.fixture
def host(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    home.mkdir()
    sources = _plant_sources(workspace)
    descriptors = _plant_descriptors(home)
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    return {"home": home, "sources": sources, "descriptors": descriptors}


def test_the_planted_sources_resolve_from_the_registry_pointers(host):
    # The condition under test is real: each pointer finds its planted folder.
    for name in HELD:
        found = resolve_source_repo(LANES[name], REPO, os.environ)
        assert found == host["sources"][name].resolve(), name


def test_empty_plans_measure_every_held_lane_as_no_frozen_launch(host):
    rows = smoke.load_expectations()
    receipt = smoke.run_lane_smoke({}, {name: rows[name] for name in HELD},
                                   home=host["home"], timeout=5, model_server=False)
    for name in HELD:
        measured = receipt["lanes"][name]
        assert measured["level"] == "no_frozen_launch", name
        assert measured["reason"] == "no_frozen_launch", name
    assert receipt["failures"] == []
    assert receipt["verdict"] == "BELOW_BAR_EXPECTED"
    assert set(receipt["lanes"]) == set(HELD)


def test_expectations_still_cover_every_registry_lane_and_hold_the_held_rows():
    rows = smoke.load_expectations()
    assert set(rows) == set(LANES)
    for name in HELD:
        assert rows[name]["expected"] == "no_frozen_launch", name


def test_the_smoke_environment_never_carries_the_workspace_root(host):
    env = smoke.smoke_environ(host["home"])
    assert "FLYWHEEL_WORKSPACE_ROOT" not in env
    assert "FLYWHEEL_WORKSPACE_ROOTS" not in env
    assert env["FLYWHEEL_HOME"] == str(host["home"])


@pytest.mark.parametrize("profile", ["auto", "source"])
def test_the_frozen_selection_holds_each_lane_with_a_source_and_a_descriptor(host, profile):
    environ = smoke.smoke_environ(host["home"])
    executable = str(host["home"] / "flywheel.exe")
    for name in HELD:
        launch, selected, component, codes = lrf.select_frozen_launch(
            LANES[name], profile, executable, environ, lambda _module: True)
        assert launch is None and component is None, name
        assert "lane_held" in codes and lrf.is_blocking("lane_held"), name
        runtime = lane_runtime.resolve_lane_runtime(
            name, LANES, {name: {"runtime_profile": profile}}, environ=environ,
            python_executable=executable, is_frozen=True,
            source_resolver=lambda _lane, n=name: host["sources"][n],
            extra_roots=lambda _lane: [], importable_fn=lambda _top: True,
            installed_version_fn=lambda _lane: None,
            package_runtime_version_fn=lambda _lane, _python: None)
        assert runtime.launch is None, name
        with pytest.raises(lane_runtime.LaneRuntimeError):
            runtime.require_launch()


def test_no_plan_builder_or_admission_knows_a_held_lane(host):
    rows = load_manifest_rows(REPO / "packaging" / "python-lane-payloads.jsonl")
    assert not set(HELD) & set(rows)
    assert not set(HELD) & set(HEALTH_TOOLS)
    environ = smoke.smoke_environ(host["home"])
    executable = str(host["home"] / "flywheel.exe")
    for name in HELD:
        for descriptor in (None, host["descriptors"][name]):
            admission = admit_bundled_lane(
                name, executable=executable, environ=environ, manifest_rows=rows,
                descriptor_path=descriptor, importable_fn=lambda _module: True)
            assert admission.launch is None, (name, descriptor)
            assert "bundled_lane_not_supported" in admission.blocking_codes, name


def test_the_registry_pointers_the_source_route_depends_on():
    # The installable sub-project sits one level below the outer checkout.
    assert Path(LANES["sofer"].source_repo).parts == ("state", "sofer", "sofer")
    for name in ("sofer", "array"):
        assert LANES[name].extra_source_repos == ("state/isomorph",), name
    for name in HELD:
        lane = LANES[name]
        assert lane.install_name == "" and lane.package_disabled_reason, name
        assert lane.source_repo.startswith("state/"), name
