"""The working directory and state folder each spawned lane child starts in.

A lane child used to inherit the engine's working directory. Several lanes write
relative to it (forum's ledger, mneme's database when MNEME_STATE is unset, learn
and telos state), so an engine started from an install folder wrote lane state
into that folder, and an all-users install puts it under Program Files.

Every spawned lane child now starts in ``<home>/lanes/<lane>/``, created on
launch. Five lanes get state defaults inside that folder when the operator has
not set the variable: mneme's database (``MNEME_STATE``), canon's blocks folder
(``CANON_BLOCKS_DIR``, created too, since canon answers "not a directory" for
a missing one), index's three caches under ``cache/`` (which otherwise land
under ``%LOCALAPPDATA%``), accountable-surface's receipts and journal
(receipts otherwise land in the temp folder) and relay's session store
(``RELAY_SESSION_DIR``, created; relay 0.4.0 and later otherwise keep it in a
per-user folder, which on Linux and macOS is outside the lane folder).

learn 2.0.0 reads LEARN_HOME for its state. The MCP child always receives
the lane folder so session writes match the engine's argument guards, including
when the parent or an env_allow grant supplies another LEARN_HOME.

articulate's child gets ARTICULATE_CLAUDE_CLI, the claude CLI the engine found
(claude_discovery), since its own PATH is the system folder.

relay 0.5.0 takes its write and exec grants and its root from its launch. Its
child always starts with RELAY_ALLOW_WRITE=0, RELAY_ALLOW_EXEC=0 and
RELAY_MCP_ROOT at the lane folder, whatever the engine's environment or an
env_allow grant says, so a run can neither write, run a shell nor read outside
the lane folder through relay's file tools (PINS_2026-09-26, O-3). It also
starts with RELAY_CHILD_ENV and RELAY_ALLOW_EXEC_CLI empty: with exec off no
shell child or CLI tier starts, and an empty value keeps it that way if a later
release loosens that. relay 0.5.0 also keeps PATH entries that reach a child's
folder out of git's and the bisect shell's lookups; with write and exec off and
check and test_cmd dropped, the app starts neither.

forum 1.15 reads FORUM_CHILD_ENV and FORUM_ALLOW_EXEC_CLI from its launch for
the commands it starts. The engine starts forum's MCP server with no command,
so its executor starts no child; both start empty anyway, whatever the
engine's environment or an env_allow grant says, so a later release that starts
a command from the MCP server finds no names and no unproven CLI allowed. forum
serves its gate decision tools only on a launch that carries
--allow-gate-decisions, which the engine adds to one granted T2 call of those
tools (``lane_tier_gate.widen_for_call``) and to no other launch.

gather 1.9.0 and later take network, exec and credential grants from the launch
(GATHER_ALLOW_NETWORK, GATHER_ALLOW_EXEC, GATHER_AUTH_ENV_ALLOW) and passes a
synthesizer only the names in GATHER_CHILD_ENV. The app's gather tools read a
local document or corpus and need none of them, so all four start empty,
whatever the engine's environment or an env_allow grant says. A granted T2
gather.run whose config names a network source, a command or a credential
answers GRANT_REQUIRED (PINS_2026-09-26_LATE). gather 1.9.1 also refuses a
network or device path itself (NON_LOCAL_PATH), after the engine's own path
guard; ``lane_caller`` answers either code as a fixed refusal.

Each of the three vendors safe_spawn 1.0.1, which drops a PATH entry that
reaches the lane's folder from a child's lookup and PATH. A frozen lane's PATH
is the system folder (and Git's cmd folder for index), and a pip or source
lane's is the engine's own; neither points into a lane folder, which holds no
tool. Measured on Windows for gather, relay and forum under both, 1.0.1 dropped
no entry, and every program 1.0.0 found it found too.

A spawned MCP child also gets TEMP, TMP, TMPDIR, APPDATA and LOCALAPPDATA
inside its lane folder, always, so a lane's temp and app-data writes stay in the
folder the tool policy's T1 rule names (POLICY-DECISION C-9). USERPROFILE stays
the user's: the claude CLI reads its login there. The lane CLI bridges and the
lane install keep the user's folders (``lane_env.lane_process_environment``),
since ``npm install -g`` finds its prefix under APPDATA.

A source-checkout launch starts in the lane folder too: its import root travels
in PYTHONPATH with PYTHONSAFEPATH=1. A ``python -m`` lane started in its lane
folder always gets PYTHONSAFEPATH=1, so a module file left in that folder cannot
shadow the lane's package. The forced grants, state defaults and scoped folders
apply to every spawned lane child in every install mode. Two launches keep
their own directory and still get them: a launch that names its own cwd, and
a launch of one of the engine's own ``harness.*`` modules (local-model and
writing outside a frozen build), which needs the engine's import root; the
frozen self-child modes that replace it take explicit roots instead. An http
lane spawns nothing.
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
    "relay": (("RELAY_SESSION_DIR", "sessions", True),),
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
                         ("RELAY_ALLOW_REMOTE_EXEC", "0"), ("RELAY_MCP_ROOT", "."),
                         ("RELAY_CHILD_ENV", ""), ("RELAY_ALLOW_EXEC_CLI", "")),
               "learn": (("LEARN_HOME", "."),),
               "forum": (("FORUM_CHILD_ENV", ""), ("FORUM_ALLOW_EXEC_CLI", "")),
               "gather": (("GATHER_ALLOW_NETWORK", ""), ("GATHER_ALLOW_EXEC", ""),
                          ("GATHER_AUTH_ENV_ALLOW", ""), ("GATHER_CHILD_ENV", ""))}
#: Set for every lane child, whatever the engine's environment says. A claude or
#: codex CLI that a lane starts (articulate's judge, a relay CLI tier) inherits
#: it, so the owner's capture hooks count the lane's own calls as suppressed
#: events instead of recording them as the owner's turns (trace ownership 7.1).
CAPTURE_OFF = {"FLYWHEEL_CAPTURE": "off"}


def forced_env(lane_name: str, folder: Path,
               environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """What a lane's child always starts with: capture off (CAPTURE_OFF), relay's
    launch grants ("." is the lane folder), and for articulate the claude CLI
    the engine found (O-14)."""
    out = {**CAPTURE_OFF, **{name: str(folder) if value == "." else value
                             for name, value in _FORCED_ENV.get(lane_name, ())}}
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
    """Return the launch started in the lane folder, with its state defaults,
    forced grants and scoped folders (see the module note for the two launches
    that keep their own cwd).

    The folder is created here, at launch resolution, so the child never starts
    in a missing directory. The state defaults join the launch's own
    environment; an inheriting launch gets them as overrides on top of the
    engine's environment, and only when the engine's environment lacks them."""
    if not spawns_lane_child(launch):
        return launch
    folder = ensure_lane_workdir(lane.name, environ)
    engine_module = _engine_self_module(launch)
    cwd = launch.cwd or (None if engine_module else str(folder))
    own = dict(launch.env_overrides)
    seen = own if not launch.inherit_env else {**environ, **own}
    forced = forced_env(lane.name, folder, environ)
    if cwd == str(folder) and "-m" in launch.argv[1:]:
        forced["PYTHONSAFEPATH"] = "1"
    taken = _SCOPED_NAMES | {name.upper() for name in forced}
    env = {**{k: v for k, v in own.items() if k.upper() not in taken},
           **lane_state_defaults(lane.name, folder, seen), **scoped_dirs(folder), **forced}
    return replace(launch, cwd=cwd, env_overrides=tuple(sorted(env.items())))
