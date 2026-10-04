"""Check every file a preregistration pins by sha256, in one command.

A preregistration names files and their sha256 on one line, for example

    | Scoring module | `harness/shapley_far.py`, sha256 `1917f8ed...` |

This reads those pairs (a backticked repository path and a 64-character hex
digest on the same line, where the path resolves to a file) and checks each one
with ``harness.canonical_bytes``:

    python -m harness.prereg_pins project-docs/prereg/2026-10-04-shapley-placebo.md
    python -m harness.prereg_pins DOC --rev 3bf61c735      # the blobs Git stores
    python -m harness.prereg_pins DOC --root ../other-checkout

With ``--rev`` the digests are taken over the blobs at that revision, which no
checkout setting can change; that is the canonical check. Without it the files
on disk are hashed as they are, and a file whose bytes differ only in line
endings is reported as EOL_ONLY rather than a bare DRIFT.

Exit codes: 0 every pin MATCH, 1 any DRIFT, 3 EOL_ONLY and no DRIFT, 2 no pins
found or a pinned file is missing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .canonical_bytes import EXIT, check_pin, render, worst

_PAIR = re.compile(r"`([^`\s]+)`[^`\n]*?`?(?:sha256[:\s-]*)?`?([0-9a-f]{64})`?")


def find_pins(text: str, root: Path, rev: str | None = None,
              exists=None) -> list[tuple[str, str]]:
    """(path, sha256) for each line pairing a repository file with a digest."""
    exists = exists or (lambda p: (root / p).is_file())
    pins: list[tuple[str, str]] = []
    for line in text.splitlines():
        for path, digest in _PAIR.findall(line):
            if "/" in path or "." in path:
                if exists(path) and (path, digest) not in pins:
                    pins.append((path, digest))
    return pins


def _blob_exists(root: Path, rev: str):
    import subprocess

    def exists(path: str) -> bool:
        return subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{rev}:{path}"],
                              capture_output=True).returncode == 0
    return exists


def run(doc: Path, root: Path, rev: str | None) -> int:
    if rev:
        rel = doc.resolve().relative_to(root.resolve()).as_posix()
        from .canonical_bytes import blob_bytes
        text = blob_bytes(root, rev, rel).decode("utf-8")
        pins = find_pins(text, root, rev, _blob_exists(root, rev))
    else:
        text = doc.read_text(encoding="utf-8")
        pins = find_pins(text, root)
    if not pins:
        print(f"no file pins found in {doc}", file=sys.stderr)
        return 2
    print(f"{len(pins)} file pins in {doc.name}"
          + (f", checked against git blobs at {rev}" if rev else ", checked on disk"))
    results = [check_pin(root, path, digest, rev) for path, digest in pins]
    for r in results:
        print(render(r))
    verdict = worst([r.verdict for r in results])
    print(f"verdict: {verdict}")
    return EXIT[verdict]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.prereg_pins",
                                 description=__doc__.split("\n\n")[0])
    ap.add_argument("doc", type=Path, help="the preregistration document")
    ap.add_argument("--root", type=Path, default=Path("."),
                    help="repository root the pinned paths are relative to")
    ap.add_argument("--rev", help="hash the blobs Git stores at this revision")
    a = ap.parse_args(argv)
    doc = a.doc if a.doc.is_absolute() or a.doc.exists() else a.root / a.doc
    try:
        return run(doc, a.root, a.rev)
    except (FileNotFoundError, UnicodeDecodeError, ValueError) as exc:
        print(f"UNVERIFIABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
