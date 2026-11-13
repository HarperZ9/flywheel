"""workspace_run.py -- a sandboxed command that may write in the project folder.

`sandboxed_run` keeps a command inside the OS sandbox. This module decides
what that command may write, and checks afterwards what it did write:

  allowed    the project root, and the run's own scratch folder (TEMP, HOME)
  refused    everything else: the user's home, Flywheel's own state, any path
             reached through `..` or a link that leads out of the root. The
             kernel refuses these on each backend.
  put back   the guarded paths inside the root (git hooks, git config beyond
             an allowlist, the session's permission, hook and MCP files).
             `workspace_guard` compares them before and after.

A project that cannot be opened safely runs with the root read-only and the
output says why. That covers an administrator's pin, the user's own opt-out,
and a root that contains the home folder or Flywheel's state: opening such a
root would open the very folders the boundary exists to keep closed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import workspace_guard

__all__ = ["WRITES_ENV", "Workspace", "open_workspace", "workspace_run"]

#: Set to 0 to keep the project read-only to commands, as it was before.
WRITES_ENV = "FLYWHEEL_WORKSPACE_WRITES"
_OFF = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class Workspace:
    """Whether commands may write in `root`, and why not when they may not."""

    root: Path
    writable: bool
    reason: str = ""

    def kernel_paths(self) -> tuple:
        """Guarded paths that exist now, as (kind, path) for the backends.

        Git configs are left out on purpose. Git rewrites a config by renaming
        a lock file over it, which a read-only bind refuses, and safe changes
        to a config are allowed; the guard checks that file after the run.
        """
        if not self.writable:
            return ()
        names = workspace_guard.protected(self.root)
        pairs = [("dir", self.root / rel) for rel in names["hooks"]]
        pairs += [("file", self.root / rel) for rel in names["control"]]
        return tuple((kind, str(path)) for kind, path in pairs
                     if (path.is_dir() if kind == "dir" else path.is_file()))

    def posix(self) -> dict:
        """Keyword arguments for `posix_sandbox.posix_run`."""
        return {"root_writable": self.writable,
                "write_protected": self.kernel_paths()}

    def windows_namespace(self, source, work):
        from .windows_workspace import readonly_namespace, writable_namespace
        if not self.writable:
            return readonly_namespace(source, work)
        return writable_namespace(source, work,
                                  [path for _kind, path in self.kernel_paths()])


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _layout_reason(root: Path, home: Path, state: Path) -> str:
    """Why this root cannot be opened to writes, or an empty string."""
    if root == Path(root.anchor):
        return "the project root is a whole drive or filesystem"
    if _inside(home, root):
        return "the project root contains your home folder"
    if _inside(state, root) or _inside(root, state):
        return "Flywheel's own state folder and the project overlap"
    return ""


def open_workspace(root, *, environ=None, policy=None, home=None,
                   flywheel_home=None) -> Workspace:
    """Decide whether commands may write in `root`.

    An administrator's pin outranks the environment, as it does for the
    unsandboxed fallback. Every argument after `root` is injectable so the
    decision can be tested without touching the host.
    """
    from .lane_workdir import flywheel_home as default_state
    from .machine_policy import load_policy
    env = os.environ if environ is None else environ
    here = Path(root).resolve()
    pins = load_policy() if policy is None else policy
    if pins.pinned("allow_workspace_writes") is False:
        return Workspace(here, False, "a machine-wide policy keeps the project "
                         f"read-only to commands ({pins.path})")
    if str(env.get(WRITES_ENV, "")).strip().lower() in _OFF:
        return Workspace(here, False, f"{WRITES_ENV} is off")
    state = Path(flywheel_home if flywheel_home is not None else default_state(env))
    reason = _layout_reason(here, Path(home or Path.home()).resolve(), state.resolve())
    return Workspace(here, not reason, reason)


def _git_env() -> dict:
    """Let git inside the sandbox read the user's name and email.

    HOME points at the scratch folder, so git would find no identity and
    refuse to commit. The user's own config is read-only to the command.
    """
    path = Path.home() / ".gitconfig"
    if "GIT_CONFIG_GLOBAL" in os.environ or not path.is_file():
        return {}
    return {"GIT_CONFIG_GLOBAL": str(path)}


def finish(space: Workspace, before, ok: bool, out: str) -> "tuple[bool, str]":
    """Check the guarded paths and add the line that records what held."""
    if out.startswith(("[blocked]", "[denied]")):
        return ok, out
    out = out.rstrip()
    if not space.writable:
        return ok, f"{out}\n[workspace read-only: {space.reason}]"
    problems = workspace_guard.verify(space.root, before)
    if not problems:
        return ok, f"{out}\n[workspace writable: guarded paths unchanged]"
    listed = "\n".join(f"  {line}" for line in problems)
    return False, (f"{out}\n[refused] the command changed a guarded path. Git "
                   "hooks, git config beyond plain settings, and the session's "
                   f"permission, hook and MCP files stay closed to commands:\n{listed}")


def workspace_run(cmd: str, root: str, *, extra_env=None, space=None,
                  **options) -> "tuple[bool, str]":
    """Run `cmd` in the sandbox with the project writable where that is safe.

    Raises SandboxUnavailable exactly as `sandboxed_run` does: a host with no
    backend runs nothing here, and the caller owns that refusal.
    """
    from .sandboxed_runner import sandboxed_run
    space = open_workspace(root) if space is None else space
    before = workspace_guard.snapshot(space.root) if space.writable else None
    env = {**_git_env(), **(extra_env or {})}
    ok, out = sandboxed_run(cmd, root, extra_env=env, workspace=space, **options)
    return finish(space, before, ok, out)
