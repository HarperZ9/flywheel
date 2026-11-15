#!/usr/bin/env python3
"""Standalone verifier for the Witnessing Spine seal.

Pure Python standard library, no repo import. A stranger holding only the sealed
directory re-derives the seal offline:

    python verify_manifest.py [directory]

The directory defaults to this script's own directory. MANIFEST.sha256 records one
"<sha256>  <relpath>" line per sealed document; lines beginning with "#" are
comments. For each line the verifier re-reads the file bytes from disk, recomputes
hashlib.sha256, and compares to the recorded digest. It re-derives the seal from
bytes, it is not a schema check.

Exit codes:
    0  MATCH         every listed file re-derives to its recorded digest.
    1  DRIFT         a recorded digest does not re-derive from the bytes on disk.
    2  UNVERIFIABLE  MANIFEST.sha256 or a listed file is missing or unreadable.

A proven DRIFT outranks UNVERIFIABLE. When one file mismatches and another is
missing, the verdict is DRIFT, so deleting a file cannot downgrade a tamper to
"unverifiable".
"""
import hashlib
import sys
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256"
_LABELS = {0: "MATCH", 1: "DRIFT", 2: "UNVERIFIABLE"}


def _parse(text: str) -> list[tuple[str | None, str]]:
    """Return (expected_digest, relpath) for each data line. A malformed line
    yields (None, line) so it counts as unverifiable rather than silently passing."""
    entries: list[tuple[str | None, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or not rel.strip() or len(digest.strip()) != 64:
            entries.append((None, line))
            continue
        entries.append((digest.strip().lower(), rel.strip()))
    return entries


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def verify(root: Path) -> tuple[int, str]:
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return 2, f"{MANIFEST_NAME} not found in {root}"
    try:
        entries = _parse(manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        return 2, f"{MANIFEST_NAME} unreadable: {exc}"
    if not entries:
        return 2, f"{MANIFEST_NAME} lists no files"
    drift: list[str] = []
    missing: list[str] = []
    for expected, rel in entries:
        if expected is None:
            missing.append(f"malformed line: {rel}")
            continue
        target = root.joinpath(*rel.split("/"))
        if not target.is_file():
            missing.append(rel)
            continue
        try:
            actual = _digest(target)
        except OSError as exc:
            missing.append(f"{rel} ({exc})")
            continue
        if actual != expected:
            drift.append(rel)
    if drift:
        return 1, f"{drift[0]} digest does not re-derive ({len(drift)} of {len(entries)} drifted)"
    if missing:
        return 2, f"{missing[0]} missing or unreadable ({len(missing)} unverifiable)"
    return 0, f"{len(entries)} files re-derive against {MANIFEST_NAME}"


def main(argv: list[str]) -> int:
    root = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent
    if not root.is_dir():
        print(f"UNVERIFIABLE  {root} is not a directory")
        return 2
    code, detail = verify(root)
    print(f"{_LABELS[code]}  {detail}")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
