"""Native frozen-tool integration for released Mneme/Relay/Plexus."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


def test_lane_registry_tracks_released_tool_versions():
    from harness.lanes_registry import LANES

    assert LANES["mneme"].version == "0.4.1"
    assert LANES["relay"].version == "0.2.3"
    assert LANES["plexus"].version == "0.2.1"


@pytest.mark.parametrize("name", ("mneme", "plexus"))
def test_released_python_lanes_use_real_frozen_descriptors(monkeypatch, name):
    import harness.lanes as lanes
    from harness.python_lane_admission import admit_python_lane

    # Only emulate the freeze root and module presence. Descriptor loading,
    # compiled expectations and validation all run unchanged.
    root = Path(__file__).resolve().parents[1] / "packaging"
    monkeypatch.setattr(sys, "_MEIPASS", str(root), raising=False)
    monkeypatch.setattr(lanes, "_frozen", lambda: True)
    monkeypatch.setattr(lanes, "_importable", lambda module: True)
    admission = admit_python_lane(
        name, executable=sys.executable, environ={}, importable_fn=lambda module: True)
    assert admission.blocking_codes == ()
    assert admission.launch is not None
    launch = lanes.resolve_mcp_launch(name)
    assert launch.argv == (sys.executable, "--bundled-lane-mcp", name)
    assert launch.allowed_tools == (f"{name}.status", f"{name}.doctor")
    assert launch.inherit_env is False
    assert dict(launch.env_overrides).get("PYTHONSAFEPATH") == "1"


def test_released_python_lane_admission_missing_descriptor_fails_closed(monkeypatch):
    import harness.lanes as lanes

    monkeypatch.setattr(lanes, "_frozen", lambda: True)
    monkeypatch.setattr(
        "harness.python_lane_admission.default_descriptor_path",
        lambda name=None: os.devnull,
    )
    monkeypatch.setattr(
        "harness.python_lane_admission._load_descriptor",
        lambda path: (None, ("bundled_descriptor_missing",)),
    )

    for name in ("mneme", "plexus"):
        with pytest.raises(lanes.LaneRuntimeError) as exc:
            lanes.resolve_mcp_launch(name)
        assert exc.value.codes == ("bundled_descriptor_missing",)


def test_python_lane_payload_manifest_pins_released_mneme_and_plexus():
    from scripts.check_python_lane_payload_manifest import load_manifest

    rows = {row["lane"]: row for row in load_manifest()}
    assert rows["mneme"]["owner_tag"] == "v0.4.1"
    assert rows["mneme"]["owner_commit"] == "d3de14d8caa06373fe42b6cc3023285a1d3550bf"
    assert rows["mneme"]["component_descriptor"]["version"] == "0.4.1"
    assert rows["mneme"]["flywheel_registry_expected_version"] == "0.4.1"

    assert rows["plexus"]["owner_tag"] == "v0.2.1"
    assert rows["plexus"]["owner_commit"] == "31a86aaf30983c6a7a511d2636e6366fcd2b3f36"
    assert rows["plexus"]["component_descriptor"]["version"] == "0.2.1"
    assert rows["plexus"]["flywheel_registry_expected_version"] == "0.2.1"


def test_frozen_gateway_spec_stages_released_python_lane_sources():
    spec = (Path(__file__).resolve().parents[1] / "packaging" / "flywheel-gateway.spec").read_text(encoding="utf-8")
    assert 'python_lane_source_root(repo, "mneme")' in spec
    assert 'python_lane_source_root(repo, "plexus")' in spec
    assert 'PYTHON_ADMITTED_LANES = ("mneme", "plexus")' in spec
    assert "python-lane-payloads/{lane}/descriptors" in spec



def test_committed_python_lane_descriptors_match_manifest_rows():
    import json
    from scripts.check_python_lane_payload_manifest import load_manifest

    root = Path(__file__).resolve().parents[1]
    rows = {row["lane"]: row for row in load_manifest()}
    for lane in ("mneme", "plexus"):
        path = root / "packaging" / "python-lane-payloads" / lane / "descriptors" / f"{lane}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == rows[lane]["component_descriptor"]
