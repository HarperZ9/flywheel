"""check_path_length.py -- no tracked path longer than 180 characters.

A first clone on Windows runs without core.longpaths. Measured with Git for
Windows 2.52 on Windows 11, a checkout then cannot create a file whose full
path reaches 260 characters, or a directory whose full path reaches 248. The
full path is the clone directory, one separator, and the tracked path. A tree
whose longest file path is F characters and whose longest directory path is D
therefore checks out only from a clone directory of at most
min(258 - F, 246 - D) characters. The directory case stops the checkout with
"Filename too long". The file case printed the same error, left the file
missing, and still exited 0.

The check exists because a benchmark run wrote its output under a path that
repeated its own root, and 38 files were committed at paths up to 206
characters, in a directory of 195. That capped the clone directory at 51
characters, and a reviewer cloning under an ordinary user profile path hit the
error.

With every path at 180 characters or less, any clone directory up to 68
characters works. There is no grandfather list: every tracked path must pass.

The length is counted in characters of the repository-relative path exactly
as `git ls-files` prints it, with forward slashes. The script exits 1 when a
path is too long. It exits 2 when git cannot list the tracked files or a
tracked path is not valid UTF-8, since such a path has no length in
characters. A broken checkout never reads as clean.
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
    return [_decode_path(raw) for raw in proc.stdout.split(b"\0") if raw]


def _decode_path(raw: bytes) -> str:
    """One path from `git ls-files -z`, or RuntimeError if it is not UTF-8."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"tracked path is not valid UTF-8: {raw!r}") from exc


def too_long(paths: list[str], limit: int = LIMIT) -> list[tuple[str, int]]:
    """Each path longer than `limit` characters, longest first."""
    over = [(p, len(p)) for p in paths if len(p) > limit]
    return sorted(over, key=lambda item: (-item[1], item[0]))


def main(root: Path | None = None, limit: int = LIMIT) -> int:
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    try:
        paths = tracked_paths(root)
    except (OSError, RuntimeError) as exc:
        print(f"path length gate could not read the tracked paths: {exc}")
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
