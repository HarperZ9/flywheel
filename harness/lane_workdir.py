"""The working directory and state folder each spawned lane child starts in.

A lane child used to inherit the engine's working directory. Several lanes write
relative to it (forum's ledger, mneme's database when MNEME_STATE is unset, learn
and telos state), so an engine started from an install folder wrote lane state
into that folder, and an all-users install puts it under Program Files.

Every spawned lane child now starts in ``<home>/lanes/<lane>/``, created on
launch. Two lanes get a state default inside that folder when the operator has
not set the variable: mneme's database (``MNEME_STATE``) and canon's blocks
folder (``CANON_BLOCKS_DIR``, created too, since canon answers "not a
directory" for a missing one).

Two launches keep their own directory. A source-checkout launch already names
its checkout as cwd, and the tests for source mode rely on that. A launch of one
of the engine's own ``harness.*`` modules (local-model and writing outside a
frozen build) needs the engine's import root as cwd; the frozen self-child modes
that replace it take explicit roots instead. An http lane spawns nothing.
"""
from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .mcp_client import LaunchSpec

_SAFE_LANE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_STATE_FILES = {"mneme": ("MNEME_STATE", "mneme.db")}
_STATE_DIRS = {"canon": ("CANON_BLOCKS_DIR", "blocks")}


def flywheel_home(environ: Mapping[str, str]) -> Path:
    """The Flywheel home: FLYWHEEL_HOME when set, else ``~/.flywheel``."""
    raw = environ.get("FLYWHEEL_HOME") or str(Path.home() / ".flywheel")
    return Path(os.path.expanduser(raw)).resolve()


def lane_workdir(lane_name: str, environ: Mapping[str, str]) -> Path:
    """``<home>/lanes/<lane>`` for a safe lane name; nothing is created."""
    if not isinstance(lane_name, str) or not _SAFE_LANE.fullmatch(lane_name):
        raise ValueError("lane name is not a safe folder name")
    return flywheel_home(environ) / "lanes" / lane_name


def ensure_lane_workdir(lane_name: str, environ: Mapping[str, str]) -> Path:
    """Create the lane folder, and any state folder the lane defaults into."""
    folder = lane_workdir(lane_name, environ)
    folder.mkdir(parents=True, exist_ok=True)
    if lane_name in _STATE_DIRS:
        (folder / _STATE_DIRS[lane_name][1]).mkdir(exist_ok=True)
    return folder


def is_lane_workdir(cwd: str | None, lane_name: str | None,
                    environ: Mapping[str, str]) -> bool:
    """True when ``cwd`` is the lane folder this module would pin."""
    if not cwd or not lane_name:
        return False
    try:
        return Path(cwd) == lane_workdir(lane_name, environ)
    except ValueError:
        return False


def lane_state_defaults(lane_name: str, folder: Path,
                        environ: Mapping[str, str]) -> dict[str, str]:
    """State variables that default into the lane folder when the operator left
    them unset. A name already present in ``environ`` (any case) wins."""
    present = {str(key).upper() for key in environ}
    spec = _STATE_FILES.get(lane_name) or _STATE_DIRS.get(lane_name)
    if spec is None or spec[0] in present:
        return {}
    return {spec[0]: str(Path(folder) / spec[1])}


def spawns_lane_child(launch: LaunchSpec | None) -> bool:
    """True for a launch that starts a lane process of its own."""
    return bool(launch is not None and launch.argv and not launch.url)


def _engine_self_module(launch: LaunchSpec) -> bool:
    argv = launch.argv
    return any(arg == "-m" and index + 1 < len(argv)
               and argv[index + 1].startswith("harness.")
               for index, arg in enumerate(argv))


def pin_lane_workdir(lane, launch: LaunchSpec | None,
                     environ: Mapping[str, str]) -> LaunchSpec | None:
    """Return the launch started in the lane folder, with its state defaults.

    The folder is created here, at launch resolution, so the child never starts
    in a missing directory. The state defaults join the launch's own
    environment; an inheriting launch gets them as overrides on top of the
    engine's environment, and only when the engine's environment lacks them."""
    if (not spawns_lane_child(launch) or launch.cwd
            or _engine_self_module(launch)):
        return launch
    folder = ensure_lane_workdir(lane.name, environ)
    own = dict(launch.env_overrides)
    seen = own if not launch.inherit_env else {**environ, **own}
    env = {**own, **lane_state_defaults(lane.name, folder, seen)}
    return replace(launch, cwd=str(folder),
                   env_overrides=tuple(sorted(env.items())))
