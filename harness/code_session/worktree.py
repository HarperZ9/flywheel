"""worktree.py -- `flywheel code --worktree NAME`: work on a separate checkout.

The session runs in a git worktree at <repo>-worktrees/NAME, beside the
repository, on a new branch flywheel/NAME started from the current HEAD. It sits
outside the repository (and outside any .flywheel folder, which the pre-action
monitor keeps the agent from writing to) so the main checkout's status stays
clean. Uncommitted work comes
along: tracked changes are applied as a patch and untracked files that are not
ignored are copied, so the agent starts from the tree you see, not from the
last commit. Your own checkout is never touched. When the session ends, the
branch holds whatever the agent changed; merge it, or remove the worktree with
`git worktree remove`. A name already in use is reused, so `--worktree NAME`
again continues in the same place.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorktreeError(RuntimeError):
    """The worktree could not be made; the message says why."""


@dataclass
class Worktree:
    path: str
    branch: str
    created: bool
    carried: list

    def record(self) -> dict:
        return {"path": self.path, "branch": self.branch, "created": self.created,
                "carried": self.carried[:50], "carried_count": len(self.carried)}


def _git(args, cwd, *, input_text=None, check=True):
    from harness import safe_program
    argv, env = safe_program.launch(["git", *args], cwd=cwd)
    p = subprocess.run(argv, cwd=cwd, env=env, input=input_text, capture_output=True,
                       text=True, timeout=120)
    if check and p.returncode != 0:
        raise WorktreeError(f"git {' '.join(args[:2])} failed: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def worktrees_dir(top: Path) -> Path:
    return top.parent / f"{top.name}-worktrees"


def repo_top(root: str) -> Path:
    try:
        return Path(_git(["rev-parse", "--show-toplevel"], root).strip())
    except (WorktreeError, OSError) as e:
        raise WorktreeError(f"--worktree needs a git repository: {e}") from e


def _carry(top: Path, dest: Path) -> list:
    """Bring uncommitted tracked changes and untracked files into dest."""
    carried = []
    patch = _git(["diff", "HEAD", "--binary"], str(top))
    if patch.strip():
        _git(["apply", "--whitespace=nowarn", "-"], str(dest), input_text=patch)
        carried += [line[6:] for line in patch.splitlines() if line.startswith("+++ b/")]
    for rel in _git(["ls-files", "--others", "--exclude-standard", "-z"], str(top)).split("\0"):
        if not rel:
            continue
        src, out = top / rel, dest / rel
        if src.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            carried.append(rel)
    return carried


def open_worktree(root: str, name: str) -> Worktree:
    if not _NAME.match(name or ""):
        raise WorktreeError("worktree names use letters, digits, dot, dash and underscore")
    top = repo_top(root)
    dest = worktrees_dir(top) / name
    branch = f"flywheel/{name}"
    if (dest / ".git").exists():
        return Worktree(str(dest), branch, created=False, carried=[])
    exists = _git(["branch", "--list", branch], str(top)).strip()
    args = ["worktree", "add", str(dest), branch] if exists else \
        ["worktree", "add", "-b", branch, str(dest), "HEAD"]
    _git(args, str(top))
    return Worktree(str(dest), branch, created=True, carried=_carry(top, dest))
