"""patch_paths.py -- the files a unified diff writes, read one way everywhere.

`apply_patch` accepts any `--- X` / `+++ Y` header pair and strips an optional
`a/` or `b/` prefix. The fingerprint, the completion report and the integrity
check must read the same targets the tool writes, or a patch with a plain
`+++ tests/test_x.py` header is applied while every check reads it as touching
nothing. This module is that one reading. Standard library only.
"""
from __future__ import annotations


def strip_ab(path: str) -> str:
    return path[2:] if path[:2] in ("a/", "b/") else path


def patch_target_paths(patch) -> list[str]:
    """Each relative path a unified diff creates or modifies, in order.

    A header pair is a `--- ` line followed by a `+++ ` line, as the tool reads
    it. A `+++ /dev/null` target (a deletion the tool does not perform) is
    skipped."""
    lines = str(patch or "").replace("\r\n", "\n").split("\n")
    paths = []
    for old, new in zip(lines, lines[1:]):
        if old.startswith("--- ") and new.startswith("+++ "):
            rel = strip_ab(new[4:].strip())
            if rel and rel != "/dev/null" and rel not in paths:
                paths.append(rel)
    return paths
