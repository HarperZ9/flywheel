"""local_git.py — optional git integration for the local agent (aider-style).

After an agentic edit run, optionally stage and commit the changes, so every edit
the local model makes is version-controlled and revertible. The commit message
carries the session ledger checkpoint, and — given the ledger's witnessed edit set
— it stages ONLY the files the ledger recorded as write/edit targets, so the
commit binds the witnessed trajectory rather than whatever else the working tree
happens to contain (a dirty file, or a file a shell wrote that the ledger never
recorded as content). It never creates a repo and never pushes; it only commits
inside an existing repo, and only when there are changes.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from ._vendor import safe_spawn
from .child_env import guarded_path_env


@dataclass
class GitRepo:
    root: str
    run: "callable" = None      # inject (args:list)->obj(returncode,stdout,stderr) for tests
    _start: "tuple | None" = field(default=None, init=False, repr=False)

    def _git(self) -> tuple:
        """git's absolute path and the environment it runs with, looked up once.

        Each lookup reads every PATH entry, which takes about a second where PATH
        is long and slow to read (WSL with the Windows PATH appended), so a GitRepo
        looks once. Build a new one to see a changed PATH.
        """
        if self._start is None:
            try:  # an absolute git, never one in the server's folder or the repo
                git = safe_spawn.resolve("git", cwd=self.root)
            except safe_spawn.SpawnRefused as e:
                raise OSError(str(e)) from e
            # git starts a filter, gpg or a hook's tools by bare name: guard its PATH too
            self._start = (git, guarded_path_env(self.root))
        return self._start

    def _run(self, *args):
        if self.run is not None:
            return self.run(list(args))
        git, env = self._git()
        return subprocess.run([git, "-C", self.root, *args],
                              capture_output=True, text=True, timeout=30, env=env)

    def is_repo(self) -> bool:
        try:
            r = self._run("rev-parse", "--is-inside-work-tree")
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and r.stdout.strip() == "true"

    def is_dirty(self) -> bool:
        return bool(self._run("status", "--porcelain").stdout.strip())

    def commit_all(self, message: str, paths: "list | None" = None) -> dict:
        """Commit staged changes. Never inits, never pushes. With `paths`, stage
        ONLY those (the witnessed edit set) so the commit binds what the ledger
        recorded, not arbitrary working-tree state; with paths=None, stage
        everything (`add -A`) for a caller that opts into that explicitly."""
        if not self.is_repo():
            return {"committed": False, "reason": "not a git repo"}
        if not self.is_dirty():
            return {"committed": False, "reason": "no changes to commit"}
        if paths is None:
            self._run("add", "-A")
        elif not paths:
            return {"committed": False, "reason": "no witnessed edits to commit"}
        else:
            self._run("add", "--", *paths)
        c = self._run("commit", "-m", message)
        if c.returncode != 0:
            return {"committed": False, "reason": (c.stderr or "commit failed").strip()[:200]}
        sha = self._run("rev-parse", "--short", "HEAD").stdout.strip()
        return {"committed": True, "sha": sha}


def commit_run(root: str, goal: str, checkpoint: str, *,
               paths: "list | None" = None, run=None) -> dict:
    """Commit the changes from an agent run, tying the message to the ledger
    checkpoint. When `paths` (the ledger's witnessed edit set) is given, only those
    files are staged, so the commit binds exactly the witnessed edits."""
    summary = goal.strip().splitlines()[0][:60] if goal.strip() else "local-agent edit"
    message = f"local-agent: {summary}\n\nledger-checkpoint: {checkpoint}"
    if paths is not None:
        message += f"\nwitnessed-edits: {len(paths)} file(s)"
    return GitRepo(root, run=run).commit_all(message, paths=paths)
