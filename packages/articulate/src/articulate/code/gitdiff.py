"""articulate.code.gitdiff -- read a change set's files from git.

Runs `git diff --name-status` and `git show` as plain argument lists, with no
shell. Python files only: the analyzer reads nothing else, and other test files
are listed as unverifiable by the report. Standard library only.
"""
from __future__ import annotations

import subprocess

from .report import FileChange


class GitError(RuntimeError):
    pass


def _git(repo, *args) -> "bytes":
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {' '.join(args[:2])} failed: {message}")
    return proc.stdout


def _show(repo, ref, path) -> str:
    return _git(repo, "show", f"{ref}:{path}").decode("utf-8", "replace")


def changes_between(repo, base, head) -> list:
    """FileChange for every file that differs between two commits. Non-Python
    files carry no text, only their path, so the report can list them."""
    raw = _git(repo, "diff", "--name-status", "-M", "-z", "--no-color", base, head)
    fields = raw.decode("utf-8", "replace").split("\0")
    out, i = [], 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[:1] in ("R", "C"):
            old, new = fields[i + 1], fields[i + 2]
            i += 3
        else:
            old = new = fields[i + 1]
            i += 2
        kind = status[:1]
        if not new.endswith(".py") and not old.endswith(".py"):
            out.append(FileChange(new, None, None))
            continue
        before = None if kind == "A" else _show(repo, base, old)
        after = None if kind == "D" else _show(repo, head, new)
        out.append(FileChange(new, before, after))
    return out
