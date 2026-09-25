"""The environment a pip or npm lane MCP server starts with.

A lane is separately packaged code, so it gets a minimal allowlisted environment
instead of the gateway's whole one. Three sources feed it, in this order:

  1. BASE_NAMES: what a Python or Node process needs to start and find its files
     on Windows, macOS and Linux (PATH, system roots, temp and home directories,
     locale, CA bundles, the Flywheel home and workspace roots).
  2. The lane's manifest declaration (Lane.env_vars): non-secret configuration
     names the lane's own source reads.
  3. The operator's grant: a per-lane ``env_allow`` list of names in the lane
     registry (~/.flywheel/lanes.json). This is the only way a credential such as
     a provider API key reaches a lane, and it is one lane and one name at a time.

Everything else is dropped. Proxy variables are left out of the base set on
purpose, since a proxy URL can carry a user name and password; grant them by name
when a lane needs them. The launch's own overrides (PYTHONPATH for a source
checkout) are applied last and win.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Mapping

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
    # TLS trust stores (paths, not secrets)
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
    # Flywheel state locations a lane may be pointed at
    "FLYWHEEL_HOME", "FLYWHEEL_WORKSPACE_ROOT", "FLYWHEEL_WORKSPACE_ROOTS",
))
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")


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
    both count; the parent's own spelling is kept."""
    wanted = BASE_NAMES | {name.upper() for name in (*declared, *granted)}
    return {key: str(value) for key, value in environ.items()
            if isinstance(key, str) and key.upper() in wanted}


def confine_lane_launch(lane, launch: LaunchSpec | None, environ: Mapping[str, str],
                        row: Mapping[str, object]) -> tuple[LaunchSpec | None, tuple[str, ...]]:
    """Return the launch with ambient inheritance replaced by the minimal env.

    Only a spawned pip or npm launch that still inherits is changed. A launch
    that already carries its own environment (bundled admission) and an http
    lane (nothing spawned) pass through unchanged."""
    granted, codes = operator_grants(row)
    if (launch is None or not launch.argv or not launch.inherit_env
            or lane.kind not in CONFINED_KINDS):
        return launch, codes
    env = lane_child_environment(environ, tuple(lane.env_vars), granted)
    env.update(launch.env_overrides)
    return replace(launch, env_overrides=tuple(sorted(env.items())),
                   inherit_env=False), codes
