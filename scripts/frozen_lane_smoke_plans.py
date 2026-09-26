"""Lane smoke plans for the frozen lanes that have no payload row.

learn and telos run the staged scripts on the bundled Node; writing runs the
engine's ``--lane-mcp writing``; local-model runs the engine's ``--mcp --root``
on a picked project folder. None of them is admitted from a payload row, so the
payload planner in frozen_gateway_lane_smoke never saw them. Each plan here goes
through the engine's own selection (lane_runtime_frozen) and confinement
(lane_env), under the smoke's environment and home.

local-model gets a project folder beside the smoke home, since a folder inside
the Flywheel home is refused. writing and local-model inherit the engine's
environment in the app; here that environment is the smoke's, passed whole, so
the runner's own variables never reach the child.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

HEALTH_TOOLS = {"learn": "learn_status", "telos": "telos.status",
                "writing": "writing.status", "local-model": "local-model.status"}


def _node_version(path: str) -> str | None:
    from harness.tool_discovery import node_version
    return node_version(path)


def _finder(environ, *, bundled=None):
    from harness.tool_discovery import find_node
    return find_node(environ, bundled=bundled, node_version=_node_version)


def _pick_project(home: Path, environ: Mapping[str, str], project: Path) -> None:
    from harness.lane_runtime_frozen import local_model_root_file
    project.mkdir(parents=True, exist_ok=True)
    target = local_model_root_file(environ)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(project.resolve()), encoding="utf-8")


def frozen_lane_plans(executable: Path, home: Path, environ: Mapping[str, str],
                      project: Path) -> dict:
    """One LanePlan per lane in HEALTH_TOOLS, launched as the engine would."""
    from harness import lane_runtime_frozen as lrf
    from harness.lane_env import confine_lane_launch
    from harness.lanes_registry import LANES
    from scripts.frozen_gateway_lane_smoke import LanePlan
    _pick_project(home, environ, project)
    stage = Path(executable).parent / "_internal" / "node-lanes"
    plans = {}
    for name, health in HEALTH_TOOLS.items():
        launch, _selected, _component, codes = lrf.select_frozen_launch(
            LANES[name], "auto", str(executable), environ, lambda _module: True,
            stage_root=stage, find=_finder)
        launch, _ = confine_lane_launch(LANES[name], launch, environ, {})
        if launch is not None and launch.inherit_env:
            env = {**environ, **dict(launch.env_overrides)}
            launch = replace(launch, env_overrides=tuple(sorted(env.items())),
                             inherit_env=False)
        plans[name] = LanePlan(launch, health, tuple(c for c in codes if lrf.is_blocking(c)))
    return plans
