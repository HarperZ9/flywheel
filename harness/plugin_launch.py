"""The environment a plugin or lane MCP launch gets on a restricted path.

A restricted path (an admitted agent.run MCP server, a credential-bound plugin
call) rebuilds the launch environment from a strict set of names plus the
credential slots it binds. Split out of plugins.py, which re-exports these.
"""
from __future__ import annotations

import os

_WINDOWS_ENV = frozenset((
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"))
_POSIX_ENV = frozenset(("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"))
_LAUNCH_OWN_ENV = frozenset(("PYTHONPATH", "PYTHONSAFEPATH"))


class PluginPermissionError(RuntimeError):
    """A fixed non-enumerating launch/metadata refusal."""

    code = "PERMISSION_REQUIRED"

    def __init__(self) -> None:
        super().__init__(self.code)


def _restricted_launch(command, bindings, slots, *, lane: bool = False):
    """Restrict a launch's env to the strict set plus its bound slots.

    A launch that inherits is rebuilt from the host env. A lane launch that
    already has inherit_env=False carries the lane env (lane_env.py), which is
    wider than the strict set and holds lanes.json env_allow grants, and a
    restricted launch is stored in discovery receipts; its env is filtered to
    the strict set plus its own import path. A frozen build's bundled lane
    child already carries its own small env and passes through."""
    from dataclasses import replace
    from .mcp_client import LaunchSpec
    platform = "windows" if os.name == "nt" else "posix"
    strict = _WINDOWS_ENV if platform == "windows" else _POSIX_ENV
    if isinstance(command, LaunchSpec) and not slots and not command.inherit_env:
        if not lane or command.argv[1:2] == ("--bundled-lane-mcp",):
            return command
        return replace(command, env_overrides=tuple(
            (key, value) for key, value in command.env_overrides
            if key.upper() in strict | _LAUNCH_OWN_ENV))
    try:
        child_env = bindings.child_environment(os.environ, platform=platform)
    except Exception:
        raise PluginPermissionError from None
    allowed = strict | set(slots)
    if (type(child_env) is not dict or set(slots) - set(child_env)
            or set(child_env) - allowed
            or any(type(key) is not str or type(value) is not str
                   for key, value in child_env.items())):
        raise PluginPermissionError
    spec = command if isinstance(command, LaunchSpec) else LaunchSpec(tuple(command))
    child_env.update((key, value) for key, value in spec.env_overrides
                     if key.upper() in _LAUNCH_OWN_ENV)
    return LaunchSpec(
        spec.argv, spec.cwd, tuple(sorted(child_env.items())), False,
        url=spec.url, hide_window=spec.hide_window, allowed_tools=spec.allowed_tools)


def _launch(command, slots, bindings, kind=None):
    if bindings is None:
        if slots:
            raise PluginPermissionError
        return command
    return _restricted_launch(command, bindings, slots, lane=kind == "lane")
