"""The working directory and state folder each spawned lane child starts in.

A lane child used to inherit the engine's working directory. Several lanes write
relative to it (forum's ledger, mneme's database when MNEME_STATE is unset, learn
and telos state), so an engine started from an install folder wrote lane state
into that folder, and an all-users install puts it under Program Files.

Every spawned lane child now starts in ``<home>/lanes/<lane>/``, created on
launch. Four lanes get state defaults inside that folder when the operator has
not set the variable: mneme's database (``MNEME_STATE``), canon's blocks folder
(``CANON_BLOCKS_DIR``, created too, since canon answers "not a directory" for
a missing one), index's three caches under ``cache/`` (which otherwise land
under ``%LOCALAPPDATA%``) and accountable-surface's receipts and journal
(receipts otherwise land in the temp folder).

articulate's child gets ARTICULATE_CLAUDE_CLI, the claude CLI the engine found
(claude_discovery), since its own PATH is the system folder.

relay 0.3.0 takes its write and exec grants and its root from its launch. Its
child always starts with RELAY_ALLOW_WRITE=0, RELAY_ALLOW_EXEC=0 and
RELAY_MCP_ROOT at the lane folder, whatever the engine's environment or an
env_allow grant says, so a run can neither write, run a shell nor read outside
the lane folder through relay's file tools (PINS_2026-09-26, O-3).

A spawned MCP child also gets TEMP, TMP, TMPDIR, APPDATA and LOCALAPPDATA
inside its lane folder, always, so a lane's temp and app-data writes stay in the
folder the tool policy's T1 rule names (POLICY-DECISION C-9). USERPROFILE stays
the user's: the claude CLI reads its login there. The lane CLI bridges and the
lane install keep the user's folders (``lane_env.lane_process_environment``),
since ``npm install -g`` finds its prefix under APPDATA.

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
# lane -> (variable, path inside the lane folder, is a folder the engine creates)
_STATE_DEFAULTS = {
    "mneme": (("MNEME_STATE", "mneme.db", False),),
    "canon": (("CANON_BLOCKS_DIR", "blocks", True),),
    "index": (("INDEX_CACHE_DIR", "cache/index", True),
              ("INDEX_MCP_CACHE_DIR", "cache/mcp", True),
              ("INDEX_GRAPH_REPO_CACHE_DIR", "cache/graph", True)),
    "accountable-surface": (("ACCOUNTABLE_SURFACE_RECEIPTS", "receipts.jsonl", False),
                            ("ACCOUNTABLE_SURFACE_JOURNAL", "journal.jsonl", False)),
}
# Always replaced for a spawned MCP child: variable -> folder inside the lane folder.
SCOPED_DIRS = (("TEMP", "tmp"), ("TMP", "tmp"), ("TMPDIR", "tmp"),
               ("APPDATA", "appdata/roaming"), ("LOCALAPPDATA", "appdata/local"))
_SCOPED_NAMES = frozenset(name for name, _rel in SCOPED_DIRS)
# Always set for a lane's spawned MCP child: the launch grants a lane takes.
_FORCED_ENV = {"relay": (("RELAY_ALLOW_WRITE", "0"), ("RELAY_ALLOW_EXEC", "0"),
                         ("RELAY_ALLOW_REMOTE_EXEC", "0"), ("RELAY_MCP_ROOT", "."))}


def forced_env(lane_name: str, folder: Path,
               environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """What a lane's child always starts with: relay's launch grants ("." is the
    lane folder), and for articulate the claude CLI the engine found (O-14)."""
    out = {name: str(folder) if value == "." else value
           for name, value in _FORCED_ENV.get(lane_name, ())}
    if lane_name == "articulate" and environ is not None:
        from .claude_discovery import ENV_VAR, find_claude
        found = find_claude(environ)
        if found.found and found.path:
            out[ENV_VAR] = found.path
    return out


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
    for _name, rel, is_dir in _STATE_DEFAULTS.get(lane_name, ()):
        if is_dir:
            (folder / rel).mkdir(parents=True, exist_ok=True)
    return folder


def scoped_dirs(folder: Path) -> dict[str, str]:
    """TEMP, TMP, TMPDIR and the app-data folders inside ``folder``, created."""
    out = {}
    for name, rel in SCOPED_DIRS:
        path = Path(folder) / rel
        path.mkdir(parents=True, exist_ok=True)
        out[name] = str(path)
    return out


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
    return {name: str(Path(folder) / rel)
            for name, rel, _is_dir in _STATE_DEFAULTS.get(lane_name, ())
            if name not in present}


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
    forced = forced_env(lane.name, folder, environ)
    taken = _SCOPED_NAMES | {name.upper() for name in forced}
    env = {**{k: v for k, v in own.items() if k.upper() not in taken},
           **lane_state_defaults(lane.name, folder, seen), **scoped_dirs(folder), **forced}
    return replace(launch, cwd=str(folder),
                   env_overrides=tuple(sorted(env.items())))
