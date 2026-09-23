"""check_path_length.py -- no tracked path longer than 180 characters.

Windows caps a full path at 259 characters unless core.longpaths is set, and a
first-time clone runs with the default. A tracked path of L characters plus the
separator and the clone directory must fit under that cap, so the clone
directory can be at most about 258 - L characters. Past that, the checkout
stops with "Filename too long".

The check exists because a benchmark run wrote its output under a path that
repeated its own root, and 38 files were committed at paths up to 206
characters. That left room for a clone directory of about 52 characters, and a
reviewer cloning under an ordinary user profile path hit the error.

At 180 characters a clone directory of about 78 characters still works. There
is no grandfather list: every tracked path must pass.

The length is counted in characters of the repository-relative path exactly
as `git ls-files` prints it, with forward slashes. The script exits 1 when a
path is too long and 2 when git cannot list the tracked files, so a broken
checkout never reads as clean.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LIMIT = 180


def tracked_paths(root: Path) -> list[str]:
    """Every path git tracks under root, as `git ls-files` prints it."""
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed in {root}: {detail}")
    return [p for p in proc.stdout.decode("utf-8").split("\0") if p]


def too_long(paths: list[str], limit: int = LIMIT) -> list[tuple[str, int]]:
    """Each path longer than `limit` characters, longest first."""
    over = [(p, len(p)) for p in paths if len(p) > limit]
    return sorted(over, key=lambda item: (-item[1], item[0]))


def main(root: Path | None = None, limit: int = LIMIT) -> int:
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    try:
        paths = tracked_paths(root)
    except (OSError, RuntimeError) as exc:
        print(f"path length gate could not list tracked files: {exc}")
        return 2
    if not paths:
        print(f"path length gate found no tracked files in {root}")
        return 2
    failures = too_long(paths, limit)
    for path, n in failures:
        print(f"TOO LONG: {n} characters (limit {limit}): {path}")
    if failures:
        return 1
    longest = max(paths, key=len)
    print(f"path length gate clean: {len(paths)} tracked paths, longest "
          f"{len(longest)} characters (limit {limit}): {longest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
