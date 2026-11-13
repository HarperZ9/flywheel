"""workspace_run.py -- a sandboxed command that may write in the project folder.

`sandboxed_run` keeps a command inside the OS sandbox. This module decides
what that command may write, and checks afterwards what it did write:

  allowed    the project root, the run's own scratch folder (TEMP, HOME), and
             for a linked git worktree the folders git must write to commit
  refused    everything else: the user's home, Flywheel's own state, any path
             reached through `..` or a link that leads out of the root. The
             kernel refuses these on each backend.
  put back   the guarded paths (git hooks, git config beyond an allowlist, the
             session's permission, hook and MCP files). `workspace_guard`
             compares them before and after.

A project that cannot be opened safely runs with the root read-only and the
output says why in one line. The cases are listed in `open_workspace`.

The check after the run happens in a `finally`, so an interrupt or an error
from the sandbox still puts guarded paths back and logs what it found.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import workspace_guard, workspace_marks
from .workspace_paths import MAX_DEPTH, MAX_GIT_DIRS, protected

__all__ = ["WRITES_ENV", "Workspace", "open_workspace", "workspace_run"]

log = logging.getLogger(__name__)
#: Set to 0 to keep the project read-only to commands, as it was before.
WRITES_ENV = "FLYWHEEL_WORKSPACE_WRITES"
_OFF = frozenset({"0", "false", "no", "off"})
NO_CONTROL = ("this account lacks the WRITE_OWNER right on {path} (Modify and not Full "
              "control), which Windows needs to open a folder to the sandbox; grant it "
              "with: icacls <folder> /grant <user>:(OI)(CI)(M,WO)")


@dataclass(frozen=True)
class Workspace:
    """Whether commands may write in `root`, and why not when they may not."""

    root: Path
    writable: bool
    reason: str = ""
    state: "Path | None" = None       # the Flywheel home that holds this root's marks

    def kernel_paths(self) -> tuple:
        """Guarded paths that exist now, as (kind, path) for the backends.

        Git configs are left out on purpose. Git rewrites a config by renaming
        a lock file over it, which a read-only bind refuses, and safe changes
        to a config are allowed; the guard checks that file after the run.
        """
        if not self.writable:
            return ()
        names = protected(self.root)
        pairs = [("dir", self.root / rel) for rel in names["hooks"]]
        pairs += [("file", self.root / rel) for rel in names["control"]]
        return tuple((kind, str(path)) for kind, path in pairs
                     if (path.is_dir() if kind == "dir" else path.is_file()))

    def extra_writable(self) -> tuple:
        """Folders outside the root that git must write in a linked worktree."""
        return protected(self.root)["opened"] if self.writable else ()

    def posix(self) -> dict:
        """Keyword arguments for `posix_sandbox.posix_run`."""
        return {"root_writable": self.writable, "write_protected": self.kernel_paths(),
                "extra_writable": self.extra_writable()}

    def windows_namespace(self, source, work):
        from .windows_workspace import readonly_namespace, writable_namespace
        if not self.writable:
            return readonly_namespace(source, work)
        return writable_namespace(source, work, [path for _kind, path in self.kernel_paths()],
                                  opened=self.extra_writable(), state=self.state)


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _layout_reason(root: Path, home: Path, state: Path) -> str:
    """Why this folder cannot be opened to writes, or an empty string."""
    if root == Path(root.anchor):
        return "the project root is a whole drive or filesystem"
    if _inside(home, root):
        return "the project root contains your home folder"
    if _inside(state, root) or _inside(root, state):
        return "Flywheel's own state folder and the project overlap"
    return ""


def _windows_can_label(path) -> bool:
    if os.name != "nt":
        return True
    from .windows_label import can_label
    return can_label(path)


def _closed_reason(here: Path, env, pins, home: Path, state: Path, can_label) -> str:
    """The first reason commands may not write in `here`, or an empty string."""
    if pins.pinned("allow_workspace_writes") is False:
        return f"a machine-wide policy keeps the project read-only to commands ({pins.path})"
    if str(env.get(WRITES_ENV, "")).strip().lower() in _OFF:
        return f"{WRITES_ENV} is off"
    held = workspace_marks.hold_reason(here, state)
    if held:
        return held
    names = protected(here)
    if names["capped"]:
        return (f".git/modules holds more than {MAX_GIT_DIRS} git folders or nests deeper "
                f"than {MAX_DEPTH} levels, more than the guard reads")
    for folder in (here, *(Path(path) for path in names["opened"])):
        reason = _layout_reason(folder, home, state)
        if reason:
            return reason
        if not can_label(folder):
            return NO_CONTROL.format(path=folder)
    return ""


def open_workspace(root, *, environ=None, policy=None, home=None,
                   flywheel_home=None, can_label=None) -> Workspace:
    """Decide whether commands may write in `root`.

    Read-only, with the reason, when: an administrator pinned it closed (the
    pin outranks the environment); FLYWHEEL_WORKSPACE_WRITES is off; a hold
    is on the project; `.git/modules` is past the guard's caps; the root or a
    worktree's git folder holds the home or Flywheel's state, or is a whole
    drive; on Windows, the account cannot label the folder. Every argument
    after `root` is injectable so the decision can be tested off the host.
    """
    from .lane_workdir import flywheel_home as default_state
    from .machine_policy import load_policy
    env = os.environ if environ is None else environ
    here = Path(root).resolve()
    state = Path(flywheel_home if flywheel_home is not None else default_state(env)).resolve()
    reason = _closed_reason(here, env, load_policy() if policy is None else policy,
                            Path(home or Path.home()).resolve(), state,
                            _windows_can_label if can_label is None else can_label)
    return Workspace(here, not reason, reason, state)


def _git_env() -> dict:
    """Let git inside the sandbox read the user's name and email.

    HOME points at the scratch folder, so git would find no identity and
    refuse to commit. The user's own config is read-only to the command.
    """
    path = Path.home() / ".gitconfig"
    if "GIT_CONFIG_GLOBAL" in os.environ or not path.is_file():
        return {}
    return {"GIT_CONFIG_GLOBAL": str(path)}


def _checked(space: Workspace, before) -> list:
    """Verify the guarded paths; hold the project when a change stayed."""
    problems = workspace_guard.verify(space.root, before)
    if problems.failed:
        workspace_marks.hold(space.root, "a guarded path could not be put back after a "
                             f"command ({problems.failed[0]})", space.state)
    return list(problems)


def finish(space: Workspace, before, ok: bool, out: str) -> "tuple[bool, str]":
    """Check the guarded paths and add the line that records what held."""
    if out.startswith(("[blocked]", "[denied]")):
        return ok, out
    out = out.rstrip()
    if not space.writable:
        return ok, f"{out}\n[workspace read-only: {space.reason}]"
    problems = _checked(space, before)
    held = workspace_marks.hold_reason(space.root, space.state)
    if not problems and not held:
        return ok, f"{out}\n[workspace writable: guarded paths unchanged]"
    listed = "".join(f"\n  {line}" for line in problems)
    text = (f"{out}\n[refused] the command changed a guarded path. Git hooks, git config "
            "beyond plain settings, and the session's permission, hook and MCP files stay "
            f"closed to commands:{listed}") if problems else out
    if held:
        text += f"\n[workspace closed to commands: {held}]"
    return False, text


def _after_failure(space: Workspace, before) -> None:
    """The check for a run that ended in an exception: restore, log, annotate."""
    problems = _checked(space, before)
    for line in problems:
        log.warning("guarded path changed by an interrupted command: %s", line)
    error = sys.exception()
    if problems and error is not None:
        error.add_note("guarded paths changed and were checked: " + "; ".join(problems))


def workspace_run(cmd: str, root: str, *, extra_env=None, space=None,
                  **options) -> "tuple[bool, str]":
    """Run `cmd` in the sandbox with the project writable where that is safe.

    Raises SandboxUnavailable exactly as `sandboxed_run` does: a host with no
    backend runs nothing here, and the caller owns that refusal.
    """
    from .sandboxed_runner import sandboxed_run
    space = open_workspace(root) if space is None else space
    before = workspace_guard.snapshot(space.root) if space.writable else None
    env, finished = {**_git_env(), **(extra_env or {})}, False
    try:
        ok, out = sandboxed_run(cmd, root, extra_env=env, workspace=space, **options)
        finished = True
    finally:
        if not finished and before is not None:
            _after_failure(space, before)
    return finish(space, before, ok, out)
