"""local_git.py — optional git integration for the local agent (aider-style).

After an agentic edit run, optionally stage and commit the changes, so every edit
the local model makes is version-controlled and revertible. The commit message
carries the session ledger checkpoint, so the git history points back at the
witnessed trajectory that produced the change — a provenance bridge aider does
not have. It never creates a repo and never pushes; it only commits inside an
existing repo, and only when there are changes.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class GitRepo:
    root: str
    run: "callable" = None      # inject (args:list)->obj(returncode,stdout,stderr) for tests

    def _run(self, *args):
        if self.run is not None:
            return self.run(list(args))
        return subprocess.run(["git", "-C", self.root, *args],
                              capture_output=True, text=True, timeout=30)

    def is_repo(self) -> bool:
        try:
            r = self._run("rev-parse", "--is-inside-work-tree")
        except (OSError, subprocess.SubprocessError):
            return False
        return r.returncode == 0 and r.stdout.strip() == "true"

    def is_dirty(self) -> bool:
        return bool(self._run("status", "--porcelain").stdout.strip())

    def commit_all(self, message: str) -> dict:
        """Stage everything and commit. Never inits, never pushes."""
        if not self.is_repo():
            return {"committed": False, "reason": "not a git repo"}
        if not self.is_dirty():
            return {"committed": False, "reason": "no changes to commit"}
        self._run("add", "-A")
        c = self._run("commit", "-m", message)
        if c.returncode != 0:
            return {"committed": False, "reason": (c.stderr or "commit failed").strip()[:200]}
        sha = self._run("rev-parse", "--short", "HEAD").stdout.strip()
        return {"committed": True, "sha": sha}


def commit_run(root: str, goal: str, checkpoint: str, *, run=None) -> dict:
    """Commit the changes from an agent run, tying the message to the ledger
    checkpoint (the witnessed trajectory that produced them)."""
    summary = goal.strip().splitlines()[0][:60] if goal.strip() else "local-agent edit"
    message = f"local-agent: {summary}\n\nledger-checkpoint: {checkpoint}"
    return GitRepo(root, run=run).commit_all(message)
