"""Which launch a frozen build (the installed app's engine) performs per lane.

A frozen build has no ``python`` on PATH, often no ``node``, and none of the
lanes' console scripts, so a declared ``python -m ...``, ``node <script>`` or
``<command> mcp`` argv cannot start. This module picks the one launch the
frozen engine can perform for each lane:

- a payload lane admits from its reviewed payload through ``--bundled-lane-mcp``
  (bundled_lane_admission);
- learn runs the staged script on an absolute Node (node_lanes); a lane the
  policy holds out of the build (telos, the O-8 hold) reports ``lane_held``
  before any Node lookup;
- local-model runs the engine's ``--mcp --root <folder>`` mode on the project
  folder the person picked, read from ``<home>/lanes/local-model/root``;
- writing runs the engine's ``--lane-mcp writing`` mode (frozen_lane_modes);
- an http lane spawns nothing;
- any other lane is not in this build, and says so with a code.

Every spawned launch admits only the tool policy's T1 tools that are in the
build (``lane_tool_policy.admitted_tools``); the payload lanes carry the same
list through their reviewed rows. No launch here starts with a bare interpreter
or console script. A launch that
cannot happen returns codes instead. A setup code (``SETUP_CODES``) means the
person has a step to take; any other code is a defect of the build.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping

from . import node_lanes
from .bundled_lane_descriptor import bundled_payload_lane_names
from .lane_tool_policy import HELD_LANES, admitted_tools
from .lane_workdir import lane_workdir
from .mcp_client import LaunchSpec
from .tool_discovery import find_node

LOCAL_MODEL = "local-model"
LOCAL_MODEL_ROOT_FILE = "root"
LANE_MCP_LANES = ("writing",)
SETUP_CODES = {
    "local_model_root_unset": "project_folder",
    "local_model_root_missing": "project_folder",
    "local_model_root_protected": "project_folder",
    "node_runtime_missing": "node",
    "node_runtime_too_old": "node",
}
DEFECT_CODES = frozenset((
    "frozen_lane_not_in_build", "node_lane_not_staged", "node_lane_script_missing"))
#: A stated hold: the lane is left out of this build on purpose, not by a defect.
HOLD_CODES = frozenset(("lane_held",))
NEEDS_SETUP = "needs_setup"
CANNOT_LAUNCH = "cannot_launch"
Selection = tuple  # (launch, selected_runtime, bundled_component, codes)


def _stage_root() -> Path | None:
    """The Node lane stage of this build; a seam the tests replace."""
    return node_lanes.frozen_stage_root()


def is_blocking(code: str) -> bool:
    """True for a code that stops a frozen launch."""
    return (code.startswith("bundled_") or code in SETUP_CODES or code in DEFECT_CODES
            or code in HOLD_CODES)


def setup_items(codes) -> tuple[str, ...]:
    """The setup item ids the codes name, once each, in code order."""
    return tuple(dict.fromkeys(SETUP_CODES[c] for c in codes if c in SETUP_CODES))


def launch_state(codes) -> str | None:
    """``needs_setup`` when only setup codes block, ``cannot_launch`` for a
    defect, None when nothing blocks."""
    blocking = [code for code in codes if is_blocking(code)]
    if not blocking:
        return None
    return NEEDS_SETUP if all(code in SETUP_CODES for code in blocking) else CANNOT_LAUNCH


def select_frozen_launch(lane, profile: str, executable: str,
                         environ: Mapping[str, str],
                         importable_fn: Callable[[str], bool], *,
                         stage_root: Path | None = None,
                         find: Callable[..., object] | None = None) -> Selection:
    """The frozen launch for ``lane`` as (launch, selected, component, codes).

    ``stage_root`` and ``find`` default to this build's Node stage and Node
    discovery; the smoke passes the build it measures."""
    if lane.name in bundled_payload_lane_names():
        if lane.package_disabled_reason and profile != "auto":
            return None, "package", None, ()
        from .bundled_lane_admission import admit_bundled_lane
        admission = admit_bundled_lane(lane.name, executable=executable,
                                       environ=environ, importable_fn=importable_fn)
        return admission.launch, "bundled", admission.component, admission.blocking_codes
    if lane.kind == "http":
        return LaunchSpec(tuple(lane.mcp_command()), url=lane.endpoint()), "http", None, ()
    if lane.name in HELD_LANES:
        return None, "bundled", None, ("lane_held",)
    if lane.name in node_lanes.NODE_LANES:
        res = node_lanes.resolve_node_lane(
            lane, "frozen", environ, find=find or find_node,
            stage_root=stage_root if stage_root is not None else _stage_root())
        return res.launch, "bundled", None, res.codes
    if lane.name == LOCAL_MODEL:
        root, code = local_model_root(environ)
        if code:
            return None, "bundled", None, (code,)
        return LaunchSpec((executable, "--mcp", "--root", root), hide_window=True,
                          allowed_tools=tuple(admitted_tools(lane.name))), "bundled", None, ()
    if lane.name in LANE_MCP_LANES:
        return LaunchSpec((executable, "--lane-mcp", lane.name), hide_window=True,
                          allowed_tools=tuple(admitted_tools(lane.name))), "bundled", None, ()
    if lane.package_disabled_reason:
        # The runtime reports package_distribution_disabled with the reason.
        return None, "package", None, ()
    return None, "bundled", None, ("frozen_lane_not_in_build",)


def local_model_root_file(environ: Mapping[str, str]) -> Path:
    """``<home>/lanes/local-model/root``: one line, the picked project folder."""
    return lane_workdir(LOCAL_MODEL, environ) / LOCAL_MODEL_ROOT_FILE


def local_model_root(environ: Mapping[str, str]) -> tuple[str | None, str]:
    """The picked project folder, or (None, setup code).

    Unset or empty: ``local_model_root_unset``. Not an existing absolute folder:
    ``local_model_root_missing``. The home folder itself, or a folder inside or
    holding the Flywheel home: ``local_model_root_protected``, the same rule
    local_agent_grants applies at start (WORKSPACE_PROTECTED)."""
    try:
        text = local_model_root_file(environ).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None, "local_model_root_unset"
    if not text:
        return None, "local_model_root_unset"
    path = Path(os.path.expanduser(text))
    if not path.is_absolute() or not path.is_dir():
        return None, "local_model_root_missing"
    from .local_agent_grants import GrantRefusal, grants_from_config
    try:
        grants = grants_from_config(environ, workspace=str(path))
    except GrantRefusal:
        return None, "local_model_root_protected"
    return grants.workspace, ""
