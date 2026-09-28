"""A run's git identity, read with hardened git calls (7.8, EN-C6).

`workspace_snapshot` hashes ignored files too (`.venv`, `.env`, `dist`), and
a fresh clone lacks them, so it cannot say whether a later clone matches the
workspace a run started from. When the run root is in a git work tree, the
run's ledger gets one `workspace_git` entry: `HEAD`, a digest of
`git ls-files -s` (tracked files only) and a digest of
`git status --porcelain --untracked-files=all`, with `clean` true when that
status is empty. Ignored files do not appear in either.

A plain `git status` can run a repository-configured fsmonitor command and
rewrites `.git/index`. Every call here runs as
`git --no-optional-locks -c core.fsmonitor=false -c core.hooksPath=<none>`
with the `GIT_*` variables of the caller removed and system configuration
off, and submodules are not entered. Traces written before this change have
no git identity.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess

from . import safe_program

_log = logging.getLogger(__name__)
SCHEMA = "flywheel.workspace-git/v1"
TIMEOUT_S = 30


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1")
    return env


def git(root, *args: str, check: bool = True) -> bytes | None:
    """One hardened git call in `root`; None when git fails or is missing."""
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
               "-c", f"core.hooksPath={os.devnull}", "-c", "core.untrackedCache=false",
               "-C", str(root), *args]
    try:
        done = subprocess.run(safe_program.argv(command), capture_output=True, env=_env(),
                              timeout=TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log.warning("git %s did not run (%s)", args[0], type(exc).__name__)
        return None
    if check and done.returncode != 0:
        return None
    return done.stdout


def git_identity(root) -> dict | None:
    """HEAD and digests of tracked files and status, or None outside git."""
    inside = git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != b"true":
        return None
    head = git(root, "rev-parse", "--verify", "-q", "HEAD")
    tracked = git(root, "ls-files", "-s", "-z")
    status = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                 "--ignore-submodules=all")
    if tracked is None or status is None:
        return None
    return {"schema": SCHEMA, "head": head.strip().decode("ascii") if head else None,
            "tracked_sha256": hashlib.sha256(tracked).hexdigest(),
            "status_sha256": hashlib.sha256(status).hexdigest(), "clean": status == b""}


def commit_exists(root, head: str | None) -> bool:
    return bool(head) and git(root, "cat-file", "-e", f"{head}^{{commit}}") is not None


def record_git(root, ledger) -> dict | None:
    """Write the `workspace_git` ledger entry at run start, when in git."""
    identity = git_identity(root)
    if identity is not None:
        ledger.append("workspace_git", json.dumps(identity, sort_keys=True))
    return identity
