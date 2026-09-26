"""Operator-granted authority for the stdio server's local_agent_run tool.

Write, exec, online model tiers and the workspace a run may touch are the
operator's decision, made when the server starts. Each comes from a start flag
of ``local-agent --mcp`` or, when that flag is absent, from the environment:

  --root PATH           FLYWHEEL_LOCAL_AGENT_WORKSPACE=PATH   the workspace
  --allow-write         FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE=1    the write tools
  --allow-exec          FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC=1     the sandboxed exec tool
  --allow-online        FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE=1   online and plan-mode tiers

An explicit flag wins over the environment, in both directions: ``--root``
replaces an inherited workspace, and ``--no-allow-exec`` refuses exec even when
the environment grants it. With neither, the workspace is the server's working
directory and every grant is off. The gateway sets the workspace to its own
``--root`` for the bundled local-model lane (pin_gateway_workspace).

The tool arguments are written by the model, so they can only narrow what the
operator granted. ``allow_write``, ``allow_exec`` or ``online`` set to true
without the matching grant is refused, a non-boolean value is refused, and a
``backend`` other than a local tier needs the online grant. ``root`` must
resolve inside the workspace after symlinks, junctions and ``..`` segments are
resolved; a relative ``root`` is taken relative to the workspace. A root that
is the user's home directory itself, or that contains or sits inside the
Flywheel home (lanes.json, the gateway token, the signing keys), is refused.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

_TRUE = frozenset(("1", "true", "yes", "on"))
WORKSPACE_ENV = "FLYWHEEL_LOCAL_AGENT_WORKSPACE"


class GrantRefusal(Exception):
    """A local_agent_run argument asked for more than the operator granted."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AgentRunGrants:
    workspace: str
    allow_write: bool = False
    allow_exec: bool = False
    allow_online: bool = False
    refused: str = ""   # a start-time refusal code; every run then returns it


def refused_grants(refusal: GrantRefusal) -> AgentRunGrants:
    """Grants for a server whose start configuration was refused: no workspace,
    nothing granted, and every local_agent_run answers with the refusal code."""
    return AgentRunGrants(workspace="", refused=refusal.code)


def _flag(env: Mapping[str, str], name: str, explicit: bool | None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return str(env.get(name, "")).strip().lower() in _TRUE


def grants_from_config(environ: Mapping[str, str] | None = None, *,
                       workspace: str | None = None, allow_write: bool | None = None,
                       allow_exec: bool | None = None,
                       allow_online: bool | None = None) -> AgentRunGrants:
    """Freeze the operator's grants: an explicit argument, then the environment.

    An explicitly chosen workspace that is protected is refused here, at start,
    with WORKSPACE_PROTECTED. A default (working directory) workspace is checked
    per run instead, so a server started in the home directory still runs in a
    narrower root."""
    env = os.environ if environ is None else environ
    chosen = workspace or env.get(WORKSPACE_ENV) or None
    resolved = os.path.realpath(os.path.expanduser(chosen or os.getcwd()))
    if chosen is not None and _protected(resolved, env):
        raise GrantRefusal("WORKSPACE_PROTECTED",
                           "the workspace is the home directory or holds the Flywheel home")
    return AgentRunGrants(
        workspace=resolved,
        allow_write=_flag(env, "FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE", allow_write),
        allow_exec=_flag(env, "FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", allow_exec),
        allow_online=_flag(env, "FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE", allow_online),
    )


def pin_gateway_workspace(root, environ: MutableMapping[str, str] | None = None) -> None:
    """Make the gateway's --root the local-model lane's workspace, unless the
    operator already set one. The lane inherits the gateway's environment."""
    env = os.environ if environ is None else environ
    if not env.get(WORKSPACE_ENV):
        env[WORKSPACE_ENV] = str(Path(root).resolve())


def _requested(args: Mapping[str, object], name: str, granted: bool,
               env_name: str) -> bool:
    if name not in args:
        return granted
    value = args[name]
    if type(value) is not bool:
        raise GrantRefusal("INVALID_GRANT_ARGUMENT",
                           f"{name} must be a boolean when present")
    if value and not granted:
        raise GrantRefusal(
            "GRANT_NOT_OPERATOR_APPROVED",
            f"{name} is granted by the operator at server start "
            f"({env_name}), not by a tool argument")
    return value


def check_online(args: Mapping[str, object], grants: AgentRunGrants,
                 local_backends: frozenset[str]) -> bool:
    """Validate ``online`` and ``backend`` for one call; return whether online."""
    online = _requested(args, "online", grants.allow_online,
                        "FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE")
    backend = args.get("backend", "auto")
    if type(backend) is not str:
        raise GrantRefusal("INVALID_GRANT_ARGUMENT", "backend must be a string when present")
    if backend not in local_backends and not grants.allow_online:
        raise GrantRefusal(
            "GRANT_NOT_OPERATOR_APPROVED",
            f"backend {backend!r} is an online or plan-mode tier; the operator grants "
            "those at server start (FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE)")
    return online


def _inside(path: str, root: str) -> bool:
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _flywheel_home(env: Mapping[str, str]) -> str:
    raw = env.get("FLYWHEEL_HOME") or os.path.join(os.path.expanduser("~"), ".flywheel")
    return os.path.realpath(os.path.expanduser(raw))


def _protected(path: str, env: Mapping[str, str]) -> bool:
    home = os.path.normcase(os.path.realpath(os.path.expanduser("~")))
    fw_home = _flywheel_home(env)
    return (os.path.normcase(path) == home or _inside(fw_home, path)
            or _inside(path, fw_home))


def resolve_run(args: Mapping[str, object], grants: AgentRunGrants,
                environ: Mapping[str, str] | None = None) -> tuple[str, bool, bool]:
    """Return (root, allow_write, allow_exec) for one run, or raise GrantRefusal."""
    if grants.refused:
        raise GrantRefusal(grants.refused, "the operator's start configuration was "
                           "refused (see the server's stderr); no run is allowed")
    env = os.environ if environ is None else environ
    allow_write = _requested(args, "allow_write", grants.allow_write,
                             "FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE")
    allow_exec = _requested(args, "allow_exec", grants.allow_exec,
                            "FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC")
    raw = args.get("root", ".")
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise GrantRefusal("INVALID_ROOT", "root must be a non-empty path string")
    workspace = os.path.realpath(grants.workspace)
    root = os.path.realpath(os.path.join(workspace, os.path.expanduser(raw)))
    if not _inside(root, workspace):
        raise GrantRefusal("ROOT_OUTSIDE_WORKSPACE",
                           "root resolves outside the operator's workspace")
    if _protected(root, env):
        raise GrantRefusal("ROOT_PROTECTED",
                           "root is the home directory or holds the Flywheel home; "
                           "pass a narrower root")
    if not os.path.isdir(root):
        raise GrantRefusal("INVALID_ROOT", "root is not an existing directory")
    return root, allow_write, allow_exec
