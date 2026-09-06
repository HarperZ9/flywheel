"""workspace_clone.py -- a disposable copy of a workspace, and how it was made.

A run that can be re-derived needs a known starting state. Flywheel copies
nothing today, so a tool run mutates the tree it was measured in, and two arms
of a benchmark share one working directory. Isolating a task means giving it a
tree it can ruin.

The mechanism differs by filesystem, and the difference is worth recording
rather than hiding. A btrfs reflink and a byte-for-byte copy produce the same
tree at very different cost, so a receipt that says "copied" without saying how
cannot explain a timing to anyone reading it later. Every attempt is kept,
including the ones that failed, because the reason a host fell back to a plain
copy is a fact about that host.

The ladder per platform is a pure function, so what a Linux host would try is
assertable from a Windows run. Performing an attempt is injectable for the same
reason: the fallback order is testable without a btrfs volume, an APFS volume,
and a ReFS volume in the same test run.

A failed attempt cleans up after itself. `cp --reflink=always` can copy part of
a tree before it refuses, and a second mechanism writing into that directory
would merge two partial copies into one tree nobody made.

Not here: `git worktree`, which is cheap and carries only tracked files. That
is a different thing from a copy of a directory, and choosing it silently
because it is faster would hand a task a workspace missing every file its
author had not committed yet.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "flywheel.workspace-clone/v1"

#: What each platform tries, best first. `copy` is last everywhere and never
#: fails for a reason the ladder can route around, so it is the floor rather
#: than another rung.
LADDER = {
    "linux": ("reflink", "copy"),
    "darwin": ("clonefile", "copy"),
    "win32": ("copy",),
}

#: Mechanisms whose result shares blocks with the source until one side is
#: written. This is a statement about cost, not about visibility: a
#: copy-on-write clone is as independent as a byte copy is.
SHARED = frozenset({"reflink", "clonefile"})


@dataclass(frozen=True)
class Clone:
    """What was made, by which mechanism, and what the others said."""

    mechanism: str | None = None
    source: str = ""
    dest: str = ""
    shared: bool = False
    seconds: float = 0.0
    files: int = 0
    bytes: int = 0
    attempts: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.mechanism is not None

    def record(self) -> dict:
        """The receipt-shaped form. Every field a later reader needs to say
        why this run started where it did, and what the copy cost."""
        return {"schema": SCHEMA, "mechanism": self.mechanism,
                "source": self.source, "dest": self.dest,
                "shared": self.shared, "seconds": round(self.seconds, 4),
                "files": self.files, "bytes": self.bytes,
                "attempts": [{"mechanism": name, "refused": reason}
                             for name, reason in self.attempts]}


def ladder(platform: str | None = None) -> tuple:
    """The mechanisms this platform tries, in order.

    An unknown platform gets the floor rather than an empty ladder. A host
    Flywheel has never run on can still isolate a task, slowly.
    """
    plat = platform if platform is not None else sys.platform
    for known, rungs in LADDER.items():
        if plat.startswith(known):
            return rungs
    return ("copy",)


def _sh(argv: list) -> str | None:
    """Run one copy command. None means it worked."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True,
                              timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{type(exc).__name__}: {exc}"
    if done.returncode == 0:
        return None
    detail = (done.stderr or done.stdout or "").strip().splitlines()
    return f"exit {done.returncode}: {detail[-1] if detail else 'no output'}"


def perform(mechanism: str, source: Path, dest: Path) -> str | None:
    """Make `dest` a copy of `source` by one mechanism. None means it worked.

    The caller removes a partial `dest` between attempts, so this is free to
    fail halfway.
    """
    if mechanism == "reflink":
        return _sh(["cp", "-a", "--reflink=always", str(source), str(dest)])
    if mechanism == "clonefile":
        return _sh(["cp", "-Rc", str(source), str(dest)])
    if mechanism == "copy":
        try:
            shutil.copytree(source, dest, symlinks=True)
        except (OSError, shutil.Error) as exc:
            return f"{type(exc).__name__}: {exc}"
        return None
    return f"no such mechanism: {mechanism}"


def measure(root: Path) -> tuple:
    """Files and bytes under `root`, counted after the copy landed.

    A clone that shares its blocks still reports the bytes it stands for. The
    number answers how large a tree the task was given, which is a different
    question from how much the copy cost, and the mechanism answers that one.
    """
    files = total = 0
    for path in Path(root).rglob("*"):
        if path.is_file() and not path.is_symlink():
            files += 1
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return files, total


def clone_workspace(source, dest, *, platform: str | None = None,
                    attempt=None) -> Clone:
    """Copy `source` to `dest` by the best mechanism this host offers.

    `attempt` overrides how a rung is performed, so the fallback order can be
    exercised on a host that has only one real mechanism. It takes
    (mechanism, source, dest) and returns None or a reason.
    """
    src, dst = Path(source), Path(dest)
    run = attempt if attempt is not None else perform
    refused = []
    if not src.is_dir():
        return Clone(source=str(src), dest=str(dst),
                     attempts=[("none", f"source is not a directory: {src}")])
    if dst.exists():
        return Clone(source=str(src), dest=str(dst),
                     attempts=[("none", f"destination exists: {dst}")])
    for mechanism in ladder(platform):
        started = time.perf_counter()
        reason = run(mechanism, src, dst)
        elapsed = time.perf_counter() - started
        if reason is None:
            files, size = measure(dst)
            return Clone(mechanism=mechanism, source=str(src), dest=str(dst),
                         shared=mechanism in SHARED, seconds=elapsed,
                         files=files, bytes=size, attempts=refused)
        refused.append((mechanism, reason))
        # A half-written tree is worse than none: the next rung would copy
        # into it and produce a merge of two partial copies.
        shutil.rmtree(dst, ignore_errors=True)
    return Clone(source=str(src), dest=str(dst), attempts=refused)
