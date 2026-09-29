"""Launches for the Node lanes (learn, telos): absolute node, absolute script.

The registry declares each Node lane as ``node <entry>``, which fails twice on
an installed app: the PATH a lane child gets need not hold a Node (the app
bundles its own), so a bare ``node`` may not be found, and the entry is
relative to whatever folder the engine started in. A Node lane child keeps the
engine's own PATH (``lane_env.confine_lane_launch``); only a bundled Python
lane's is cut to the system folder. This module resolves both to absolute paths:

- frozen: the script under the staged ``_internal/node-lanes/<lane>/`` folder
  (``scripts/stage_node_lanes.py``), which carries a passing receipt;
- package: the script under the npm global root, ``<root>/<package>/<entry>``;
- source: the script under the lane's source checkout.

Node comes from ``tool_discovery.find_node``, which prefers the operator's
choice (``FLYWHEEL_NODE``, ``<home>/node_path``) and then the Node the frozen
build bundles. No usable Node gives no launch, the ``node`` setup item and a
fixed code. The child starts in ``<home>/lanes/<lane>/``, where learn keeps its
session files, and its launch admits the lane's T1 tools from the policy table.

This module decides the launch; lane_runtime wires it in (WP5).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .lane_tool_policy import admitted_tools
from .lane_workdir import ensure_lane_workdir
from .mcp_client import LaunchSpec
from .tool_discovery import MIN_NODE_MAJOR, ToolFinding, find_node

NODE_LANES = ("learn", "telos")
STAGE_DEST = "node-lanes"
STAGE_RECEIPT = "node-lane-stage.json"
MODES = ("frozen", "package", "source")
NodeFinder = Callable[..., ToolFinding]
_NOT_CHECKED = ToolFinding("node", False, None, None, "not_checked", str(MIN_NODE_MAJOR),
                           "not checked: the lane is not staged")


@dataclass(frozen=True)
class NodeLaneResolution:
    """One Node lane's launch, or the codes and setup items that stop it."""
    lane: str
    mode: str
    node: ToolFinding
    launch: LaunchSpec | None = None
    script: str | None = None
    codes: tuple[str, ...] = ()
    setup: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        return {"lane": self.lane, "mode": self.mode, "node": self.node.to_dict(),
                "script": self.script, "codes": list(self.codes), "setup": list(self.setup),
                "argv": list(self.launch.argv) if self.launch else None,
                "cwd": self.launch.cwd if self.launch else None}


def frozen_stage_root() -> Path | None:
    """``_internal/node-lanes`` in a frozen build; None elsewhere."""
    meipass = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or not meipass:
        return None
    return Path(meipass) / STAGE_DEST


def bundled_node_name(platform: str = os.name) -> str:
    """The file ``bundled_node`` looks for under ``<stage>/node``. The stage
    holds the pinned win-x64 zip's ``node.exe``; elsewhere the name is ``node``."""
    return "node.exe" if platform == "nt" else "node"


def bundled_node(stage_root: Path | None) -> Path | None:
    """The staged Node executable, when the stage holds one."""
    if stage_root is None:
        return None
    path = Path(stage_root) / "node" / bundled_node_name()
    return path if path.is_file() else None


def staged_lanes(stage_root: Path | None) -> dict[str, dict]:
    """Lane rows of a stage whose receipt says PASS; empty otherwise."""
    if stage_root is None:
        return {}
    try:
        receipt = json.loads((Path(stage_root) / STAGE_RECEIPT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(receipt, dict) or receipt.get("verdict") != "PASS":
        return {}
    return {row["lane"]: row for row in receipt.get("lanes", [])
            if isinstance(row, dict) and isinstance(row.get("lane"), str)}


def _package_root() -> Path | None:
    from .lane_runtime_support import _npm_global_root
    return _npm_global_root()


def _script(lane, mode: str, stage_root, source, package_root) -> tuple[Path | None, str]:
    """The absolute entry script, or (None, code)."""
    entry = lane.mcp_args[0]
    if mode == "frozen":
        if lane.name not in staged_lanes(stage_root):
            return None, "node_lane_not_staged"
        base = Path(stage_root) / lane.name
    elif mode == "package":
        root = package_root if package_root is not None else _package_root()
        base = Path(root) / lane.install_name if root is not None else None
    else:
        base = Path(source) if source is not None else None
    script = (base / entry).resolve() if base is not None else None
    if script is None or not script.is_file():
        return None, "node_lane_script_missing"
    return script, ""


def _runtime_code(node: ToolFinding) -> str:
    if node.found:
        return ""
    return "node_runtime_too_old" if node.version else "node_runtime_missing"


def resolve_node_lane(lane, mode: str, environ: Mapping[str, str], *,
                      stage_root: Path | None = None, source: Path | None = None,
                      package_root: Path | None = None,
                      find: NodeFinder = find_node) -> NodeLaneResolution:
    """Resolve one Node lane's launch for ``mode`` (frozen, package or source)."""
    if lane.kind != "npm" or lane.name not in NODE_LANES:
        raise ValueError(f"{lane.name} is not a Node lane")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if mode == "frozen" and stage_root is None:
        stage_root = frozen_stage_root()
    if mode == "frozen" and lane.name not in staged_lanes(stage_root):
        # A build without its stage is a defect, not a setup step.
        return NodeLaneResolution(lane.name, mode, _NOT_CHECKED, codes=("node_lane_not_staged",))
    node = find(environ, bundled=bundled_node(stage_root) if mode == "frozen" else None)
    code = _runtime_code(node)
    if code:
        return NodeLaneResolution(lane.name, mode, node, codes=(code,), setup=("node",))
    script, code = _script(lane, mode, stage_root, source, package_root)
    if script is None:
        return NodeLaneResolution(lane.name, mode, node, codes=(code,))
    launch = LaunchSpec(
        (str(node.path), str(script)), cwd=str(ensure_lane_workdir(lane.name, environ)),
        hide_window=True, allowed_tools=tuple(admitted_tools(lane.name)))
    return NodeLaneResolution(lane.name, mode, node, launch=launch, script=str(script))
