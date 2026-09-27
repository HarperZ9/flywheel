"""The environment a pip or npm lane process starts with.

A lane is separately packaged code, so it gets a minimal allowlisted environment
instead of the gateway's whole one. Three sources feed it, in this order:

  1. BASE_NAMES: what a Python or Node process needs to start and find its files
     on Windows, macOS and Linux (PATH, system roots, temp and home directories,
     locale, CA bundles, the Python import path, the Flywheel home and workspace
     roots).
  2. The lane's manifest declaration (Lane.env_vars): non-secret configuration
     names the lane's own source reads.
  3. The operator's grant: a per-lane ``env_allow`` list of names in the lane
     registry (~/.flywheel/lanes.json). A credential such as a provider API key
     reaches a lane's environment this way, one lane and one name at a time.

Everything else is dropped. Proxy variables are left out of the base set on
purpose, since a proxy URL can carry a user name and password; grant them by name
when a lane needs them. The launch's own overrides (PYTHONPATH for a source
checkout) are applied last and win.

A frozen build's bundled lane child starts from its own smaller base set
(bundled_lane_env.py) and gains sources 2 and 3 here, so a grant reaches a
bundled lane the same way it reaches a pip lane. A key saved in the app's
keychain reaches a lane only per call, through a bound credential slot
(lane_credentials.py). Every spawned lane child starts in its lane folder
(lane_workdir.py).

Two entry points use this. confine_lane_launch rewrites a lane's MCP server
launch, and lane_process_environment builds the env for every other place the
gateway runs lane code as a child process (the index, chorus, gather, crucible
and telos bridges, index router jobs, the canon context child, the package
version probe and the pip or npm install of a lane).

Stated limits. This controls environment variables only. A lane still runs
unsandboxed as the same operating-system user as the gateway, so it can read any
file that user can read, including ~/.flywheel/gateway.token, the receipt signing
key under ~/.flywheel/keys and other credential files in the home directory. It
can also write ~/.flywheel/lanes.json and grant itself an env_allow name that
takes effect on its next launch. Closing those needs a filesystem boundary for
lanes, which this module does not provide.
"""
from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .lane_workdir import ensure_lane_workdir, lane_state_defaults, pin_lane_workdir
from .mcp_client import LaunchSpec

CONFINED_KINDS = frozenset(("pip", "npm"))
BASE_NAMES = frozenset((
    # process start and executable lookup
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
    # temp, home and per-user data directories
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "USER", "USERNAME", "LOGNAME", "SHELL",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR",
    # locale, terminal and text encoding
    "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ", "TERM",
    "PYTHONIOENCODING", "PYTHONUTF8", "VIRTUAL_ENV",
    # the Python import path: a lane launched as `python -m <module>` because the
    # parent could import it must find the module the same way (paths, not secrets)
    "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
    # TLS trust stores (paths, not secrets)
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
    # Flywheel state locations a lane may be pointed at
    "FLYWHEEL_HOME", "FLYWHEEL_WORKSPACE_ROOT", "FLYWHEEL_WORKSPACE_ROOTS",
))
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_USERINFO = re.compile(r"://[^/@\s]+@")


def operator_grants(row: Mapping[str, object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The names the operator granted this lane, and a code if any were invalid."""
    raw = row.get("env_allow")
    if raw is None:
        return (), ()
    if not isinstance(raw, list):
        return (), ("env_allow_invalid",)
    names = tuple(item for item in raw
                  if isinstance(item, str) and _NAME.fullmatch(item))
    return names, (() if len(names) == len(raw) else ("env_allow_invalid",))


def lane_child_environment(environ: Mapping[str, str], declared: tuple[str, ...],
                           granted: tuple[str, ...]) -> dict[str, str]:
    """Keep only allowlisted, declared and granted names from ``environ``.

    Names match case-insensitively, so ``Path`` on Windows and ``PATH`` on POSIX
    both count; the parent's own spelling is kept. A lane-declared value that
    carries ``user:token@`` in a URL is dropped: a declared base URL passes at
    every tier, so it must not smuggle a credential. A granted name is the
    operator's own choice and keeps its value."""
    wanted = BASE_NAMES | {name.upper() for name in (*declared, *granted)}
    chosen = BASE_NAMES | {name.upper() for name in granted}
    return {key: str(value) for key, value in environ.items()
            if isinstance(key, str) and key.upper() in wanted
            and (key.upper() in chosen or not _USERINFO.search(str(value)))}


def confine_lane_launch(lane, launch: LaunchSpec | None, environ: Mapping[str, str],
                        row: Mapping[str, object]) -> tuple[LaunchSpec | None, tuple[str, ...]]:
    """Return the launch with its lane environment and lane folder.

    A spawned pip or npm launch that still inherits is rebuilt from the minimal
    env. A bundled self-child keeps its own small env and gains the lane's
    declared names and the operator's grant, so both kinds of lane see the same
    names. Every spawned lane child then starts in its lane folder
    (lane_workdir.py). An http lane (nothing spawned) passes through."""
    granted, codes = operator_grants(row)
    if launch is None or not launch.argv:
        return launch, codes
    if is_bundled_child(launch):
        launch = _grant_bundled(launch, environ, tuple(lane.env_vars), granted)
    elif launch.inherit_env and lane.kind in CONFINED_KINDS:
        env = lane_child_environment(environ, tuple(lane.env_vars), granted)
        env.update(launch.env_overrides)
        launch = replace(launch, env_overrides=tuple(sorted(env.items())),
                         inherit_env=False)
    return pin_lane_workdir(lane, launch, environ), codes


def is_bundled_child(launch: LaunchSpec) -> bool:
    """A frozen build's self-child launch of one payload lane."""
    return (not launch.inherit_env
            and tuple(launch.argv[1:2]) == ("--bundled-lane-mcp",))


def _grant_bundled(launch: LaunchSpec, environ: Mapping[str, str],
                   declared: tuple[str, ...], granted: tuple[str, ...]) -> LaunchSpec:
    """Add declared and granted names to a bundled child's own env. A name the
    bundled env already sets (PATH, the home, UTF-8) keeps its bundled value."""
    own = dict(launch.env_overrides)
    taken = {key.upper() for key in own}
    wanted = {name.upper() for name in (*declared, *granted)}
    chosen = {name.upper() for name in granted}
    for key, value in environ.items():
        if (isinstance(key, str) and key.upper() in wanted
                and key.upper() not in taken
                and (key.upper() in chosen or not _USERINFO.search(str(value)))):
            own[key] = str(value)
    return replace(launch, env_overrides=tuple(sorted(own.items())))


def lane_process_environment(lane_name: str, extra: Mapping[str, str] | None = None, *,
                             environ: Mapping[str, str] | None = None,
                             registry: Mapping[str, object] | None = None) -> dict[str, str]:
    """The env= for any child process that runs a lane's code outside its MCP launch.

    It applies the same three sources as a lane launch: BASE_NAMES, the lane's
    declared env_vars and the operator's env_allow grant for that lane. ``extra``
    carries the few values the call itself sets (a job directory, a database
    path) and wins. mneme and canon get their state defaults in the lane
    folder when neither the engine nor ``extra`` sets them. An unknown lane
    gets the base set only."""
    from .lanes_registry import LANES
    source = os.environ if environ is None else environ
    if registry is None:
        from .lanes import read_registry
        try:
            registry = read_registry()
        except (OSError, ValueError):
            registry = {}   # an unreadable registry grants nothing
    lane = LANES.get(lane_name)
    row = registry.get(lane_name) if isinstance(registry, Mapping) else None
    granted, _ = operator_grants(row if isinstance(row, Mapping) else {})
    declared = tuple(lane.env_vars) if lane is not None else ()
    env = lane_child_environment(source, declared, granted)
    env.update({str(key): str(value) for key, value in (extra or {}).items()})
    if lane is not None and lane_state_defaults(lane_name, Path(), env):
        folder = ensure_lane_workdir(lane_name, source)
        env.update(lane_state_defaults(lane_name, folder, env))
    return env
