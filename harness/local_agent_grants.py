"""Operator-granted authority for the stdio server's local_agent_run tool.

Write, exec and the workspace a run may touch are the operator's decision, made
when the server starts. They come from the server's start flags (the
``local-agent --mcp`` CLI) or its environment:

  FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE=1   let runs use the write tools
  FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC=1    let runs use the sandboxed exec tool
  FLYWHEEL_LOCAL_AGENT_WORKSPACE=PATH  the directory runs are confined to
                                       (default: the server's working directory)

The tool arguments are written by the model, so they can only narrow what the
operator granted. ``allow_write: true`` or ``allow_exec: true`` without the
matching grant is refused, a non-boolean value is refused, and ``root`` must
resolve inside the workspace after symlinks, junctions and ``..`` segments are
resolved. A relative ``root`` is taken relative to the workspace.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_TRUE = frozenset(("1", "true", "yes", "on"))


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


def grants_from_config(environ: Mapping[str, str] | None = None, *,
                       workspace: str | None = None, allow_write: bool = False,
                       allow_exec: bool = False) -> AgentRunGrants:
    """Freeze the operator's grants from start flags and the environment."""
    env = os.environ if environ is None else environ

    def flag(name: str) -> bool:
        return str(env.get(name, "")).strip().lower() in _TRUE

    chosen = env.get("FLYWHEEL_LOCAL_AGENT_WORKSPACE") or workspace or os.getcwd()
    return AgentRunGrants(
        workspace=os.path.realpath(os.path.expanduser(chosen)),
        allow_write=bool(allow_write) or flag("FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE"),
        allow_exec=bool(allow_exec) or flag("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC"),
    )


def _requested(args: Mapping[str, object], name: str, granted: bool) -> bool:
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
            f"(FLYWHEEL_LOCAL_AGENT_{name.upper()}), not by a tool argument")
    return value


def _inside(path: str, root: str) -> bool:
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def resolve_run(args: Mapping[str, object], grants: AgentRunGrants) -> tuple[str, bool, bool]:
    """Return (root, allow_write, allow_exec) for one run, or raise GrantRefusal."""
    allow_write = _requested(args, "allow_write", grants.allow_write)
    allow_exec = _requested(args, "allow_exec", grants.allow_exec)
    raw = args.get("root", ".")
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise GrantRefusal("INVALID_ROOT", "root must be a non-empty path string")
    workspace = os.path.realpath(grants.workspace)
    root = os.path.realpath(os.path.join(workspace, os.path.expanduser(raw)))
    if not _inside(root, workspace):
        raise GrantRefusal("ROOT_OUTSIDE_WORKSPACE",
                           "root resolves outside the operator's workspace")
    if not os.path.isdir(root):
        raise GrantRefusal("INVALID_ROOT", "root is not an existing directory")
    return root, allow_write, allow_exec
