"""mcp_grants.py -- write, exec and root grants for the MCP servers, set at launch.

The process that starts a relay MCP server decides whether its runs may write
or execute, with ``--allow-write`` / ``--allow-exec`` or ``RELAY_ALLOW_WRITE`` /
``RELAY_ALLOW_EXEC``. Both are off by default. It also pins the launch root,
with ``--root`` or ``RELAY_MCP_ROOT``, defaulting to the working directory.

One run gets what it asks for and the launch granted, both. A run that omits
``allow_write`` / ``allow_exec`` asks for neither, as in 0.2.5, and ``true``
asks for no more than the launch granted. Its ``root`` argument must resolve
inside the launch root.

Two couplings follow from what a shell can do. Exec implies write, because a
shell can write files, so ``allow_exec: true`` also asks for write. Narrowing
write with ``allow_write: false`` turns exec off, for the same reason. The online
codex and claude CLI tiers start an agent with its own shell, so they count as
exec.

The honest limit: the file tools are confined to the run's root, and the shell
is not. ``run``, ``test_cmd`` and ``check`` start in root and can reach any path
the server's user can. Write is also a route to code execution: a file written
into the tree runs the next time something executes it there (a git hook, a
build script, a shell profile under a home-directory root).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace

WRITE_ENV = "RELAY_ALLOW_WRITE"
EXEC_ENV = "RELAY_ALLOW_EXEC"
ROOT_ENV = "RELAY_MCP_ROOT"
REMOTE_EXEC_ENV = "RELAY_ALLOW_REMOTE_EXEC"

# Keys a launcher reads from the process environment and never from an env file.
# A run with the write grant can rewrite a file in its root, so a grant read from
# that file would be a grant the caller could hand itself on the next restart. The
# same holds for what children inherit (RELAY_CHILD_ENV), which unproven agent
# CLIs may start (RELAY_ALLOW_EXEC_CLI), and which program a CLI tier runs.
LAUNCH_ONLY_KEYS = (WRITE_ENV, EXEC_ENV, REMOTE_EXEC_ENV, ROOT_ENV, "RELAY_CHILD_ENV",
                    "RELAY_ALLOW_EXEC_CLI", "RELAY_CLAUDE_CLI", "RELAY_CODEX_CLI")

# Set by a surface that refuses exec on top of the launch grants (the remote
# surface without RELAY_ALLOW_REMOTE_EXEC) for the one request it is handling.
# A context variable rather than a request field, so no caller can set or clear it.
SURFACE_EXEC_REFUSED: ContextVar[bool] = ContextVar("relay_surface_exec_refused",
                                                    default=False)

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True)
class StartGrants:
    """What a server's runs may do at most. Exec implies write. ``root`` is the
    launch root; None means the working directory, resolved by ``pin_root``."""
    allow_write: bool = False
    allow_exec: bool = False
    root: str | None = None

    def __post_init__(self) -> None:
        if self.allow_exec and not self.allow_write:
            object.__setattr__(self, "allow_write", True)

    def as_dict(self) -> dict:
        """``root`` is None when the launch root is the server's working directory
        and has not been pinned yet (a readout from outside that process)."""
        return {"allow_write": self.allow_write, "allow_exec": self.allow_exec,
                "root": self.root, "agent_cli_tiers": self.allow_exec,
                "shell_path_confined": False}


def parse_flag(env: Mapping[str, str], name: str) -> bool:
    """Read one grant variable. An unrecognized value raises instead of guessing,
    so a typo cannot silently leave a grant on or off."""
    raw = (env.get(name) or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ValueError(f"{name} must be one of 1/true/yes/on or 0/false/no/off, got {raw!r}")


def grants_from_env(env: Mapping[str, str]) -> StartGrants:
    return StartGrants(allow_write=parse_flag(env, WRITE_ENV),
                       allow_exec=parse_flag(env, EXEC_ENV),
                       root=env.get(ROOT_ENV) or None)


def remote_grants(env: Mapping[str, str]) -> StartGrants:
    """The grants the remote surface configures. Exec needs RELAY_ALLOW_REMOTE_EXEC
    as well, and write needs its own RELAY_ALLOW_WRITE: exec implying write must
    not hand the phone a write grant when remote exec is off."""
    base = grants_from_env(env)      # validates every variable first
    return StartGrants(allow_write=parse_flag(env, WRITE_ENV),
                       allow_exec=base.allow_exec and parse_flag(env, REMOTE_EXEC_ENV),
                       root=base.root)


def grants_from_launch(*, allow_write: bool, allow_exec: bool,
                       env: Mapping[str, str], root: str | None = None) -> StartGrants:
    """Flags or environment: either one grants, and a root flag wins over the variable."""
    from_env = grants_from_env(env)
    return StartGrants(allow_write=allow_write or from_env.allow_write,
                       allow_exec=allow_exec or from_env.allow_exec,
                       root=root or from_env.root)


def launch_root(grants: StartGrants) -> str:
    """The launch root as an absolute, link-resolved path."""
    return os.path.realpath(grants.root or os.getcwd())


def pin_root(grants: StartGrants) -> StartGrants:
    """Resolve the launch root once, at launch, and refuse one that is not a directory."""
    root = launch_root(grants)
    if not os.path.isdir(root):
        raise ValueError(f"the MCP launch root ({ROOT_ENV} or --root) is not a directory: {root}")
    return replace(grants, root=root)


def _inside(path: str, root: str) -> bool:
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def run_root(grants: StartGrants, requested: str | None) -> tuple[str, bool]:
    """The root one run gets, and whether it stays inside the launch root. A
    relative ``requested`` resolves under the launch root, and links are followed
    before the check, so neither ``..`` nor a link can step outside."""
    base = launch_root(grants)
    target = os.path.realpath(os.path.join(base, requested or "."))
    return target, _inside(target, base)


def narrow(grants: StartGrants, want_write: bool | None,
           want_exec: bool | None) -> tuple[bool, bool]:
    """The effective (write, exec) for one run: what it asked for AND what the
    launch granted. ``None`` (omitted) asks for nothing. ``allow_exec: true``
    also asks for write unless ``allow_write`` is ``false``, and a run without
    write gets no exec. A surface refusal turns exec off."""
    asks_write = want_write is True or (want_exec is True and want_write is not False)
    write = grants.allow_write and asks_write
    exec_ = (grants.allow_exec and want_exec is True and write
             and not SURFACE_EXEC_REFUSED.get())
    return write, exec_


def describe(grants: StartGrants) -> str:
    """One line for a launcher's stderr."""
    def state(on: bool) -> str:
        return "granted" if on else "off"
    return (f"write {state(grants.allow_write)}, exec {state(grants.allow_exec)}, "
            f"root {launch_root(grants)}"
            + (" (the shell is not path-confined)" if grants.allow_exec else ""))
