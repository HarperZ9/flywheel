"""The lane smoke plans the frozen lanes that have no payload row.

learn, telos, writing and local-model launch in a frozen build through
lane_runtime_frozen, not through a payload row, so the smoke used to report
them as no_frozen_launch whatever the build could do. These plans put them
through the same selection and confinement the engine uses, under the smoke's
own environment, so their rows can be raised from a measurement.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.node_lanes import bundled_node_name
from scripts import frozen_lane_smoke_plans as plans_mod
from scripts.frozen_gateway_lane_smoke import smoke_environ


def _build(tmp_path: Path) -> Path:
    exe = tmp_path / "dist" / "flywheel-gateway" / "flywheel-gateway.exe"
    stage = exe.parent / "_internal" / "node-lanes"
    (stage / "node").mkdir(parents=True)
    (stage / "node" / bundled_node_name()).write_bytes(b"")
    for lane, entry in (("learn", "src/mcp.mjs"), ("telos", "demo/telos-mcp.mjs")):
        (stage / lane / entry).parent.mkdir(parents=True)
        (stage / lane / entry).write_text("", encoding="utf-8")
    (stage / "node-lane-stage.json").write_text(json.dumps(
        {"verdict": "PASS", "lanes": [{"lane": "learn"}, {"lane": "telos"}]}), encoding="utf-8")
    exe.write_bytes(b"")
    return exe


def _plans(tmp_path, monkeypatch):
    exe = _build(tmp_path)
    home, project = tmp_path / "run" / "home", tmp_path / "run" / "project"
    home.mkdir(parents=True)
    monkeypatch.setattr(plans_mod, "_node_version", lambda path: "v24.21.0")
    return exe, home, project, plans_mod.frozen_lane_plans(
        exe, home, smoke_environ(home), project)


def test_every_frozen_lane_without_a_payload_row_gets_a_plan(tmp_path, monkeypatch):
    exe, home, project, plans = _plans(tmp_path, monkeypatch)
    assert set(plans) == {"learn", "telos", "writing", "local-model"}
    for name, plan in plans.items():
        assert plan.launch is not None and not plan.blocking_codes, name
        assert Path(plan.launch.argv[0]).is_absolute(), name
        assert plan.launch.inherit_env is False, name
        assert Path(plan.launch.cwd) == home / "lanes" / name
        assert plan.health_tool == plans_mod.HEALTH_TOOLS[name]
    assert plans["writing"].launch.argv == (str(exe), "--lane-mcp", "writing")
    for lane in ("learn", "telos"):
        assert plans[lane].launch.argv[0] == str(exe.parent / "_internal" / "node-lanes"
                                                 / "node" / bundled_node_name()), lane
    assert plans["telos"].launch.argv[1].endswith("telos-mcp.mjs")
    assert plans["telos"].health_tool == "telos.status"


def test_local_model_gets_a_project_folder_outside_the_smoke_home(tmp_path, monkeypatch):
    exe, home, project, plans = _plans(tmp_path, monkeypatch)
    assert project.is_dir()
    assert plans["local-model"].launch.argv == (str(exe), "--mcp", "--root", str(project.resolve()))


def test_self_children_get_the_smoke_environment_not_the_runner_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_RUNNER_SECRET", "sk-planted-fake-value")
    _exe, home, _project, plans = _plans(tmp_path, monkeypatch)
    for name in ("writing", "local-model"):
        env = dict(plans[name].launch.env_overrides)
        assert env["FLYWHEEL_HOME"] == str(home), name
        assert "FAKE_RUNNER_SECRET" not in env, name
