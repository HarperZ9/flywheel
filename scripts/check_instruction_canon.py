#!/usr/bin/env python3
"""check_instruction_canon.py -- one canon, and every pointer proves it read it.

The workspace has one canonical set of instructions (`c:/dev/CLAUDE.md` and its
byte-identical mirror `c:/dev/AGENTS.md`). Every per-repo instruction file is a
POINTER plus that repo's delta: it declares the canon hash it was written
against, and holds no copy of the canon to drift.

This is the no-drift discipline the rest of `local-model` already applies to
numbers and public copy (`findings.py`, `check_claim_language.py`), turned on the
instructions themselves. A pointer whose declared hash does not match the current
canon has not been re-read since the canon changed, and CI says so.

  - default (no args): verify. Exit 1 if the mirror is out of sync or any pointer
    is stale.
  - `--bump`: re-sync the mirror's core to the canonical core and re-stamp every
    pointer's declared hash. The deliberate, auditable acknowledgment that the
    canon changed and the pointers were reviewed. Run it ON PURPOSE, never as a
    reflex, because it is the moment a human is supposed to look.

The canon lives outside this repo (at the workspace root, which is not itself a
git repo), so paths in the manifest are resolved against `--root`, default the
parent of this repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "project-docs" / "instruction-canon.json"

CORE = re.compile(r"<!--\s*CANON-CORE:BEGIN\s*-->(.*?)<!--\s*CANON-CORE:END\s*-->",
                  re.S)
STAMP = re.compile(r"<!--\s*canon:\s*(?P<path>[^\s]+)\s+sha256:(?P<sha>[0-9a-f]{64})\s*-->")


class CanonError(RuntimeError):
    pass


def _read(p: Path) -> str:
    if not p.exists():
        raise CanonError(f"missing file: {p}")
    return p.read_text(encoding="utf-8")


def core_hash(text: str, *, where: str) -> str:
    """Hash of the CANON-CORE block, whitespace-normalised at the line level so a
    CRLF/LF difference between drives is not a false drift."""
    m = CORE.search(text)
    if not m:
        raise CanonError(f"no CANON-CORE block in {where}")
    body = "\n".join(line.rstrip() for line in m.group(1).strip().splitlines())
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_manifest(manifest: "Path | None" = None) -> dict:
    return json.loads(_read(manifest or MANIFEST))


def resolve(root: Path, rel: str) -> Path:
    return (root / rel).resolve()


def verify(root: Path, manifest: "Path | None" = None) -> list[str]:
    man = load_manifest(manifest)
    problems: list[str] = []
    canon_path = resolve(root, man["canonical"])
    canon = core_hash(_read(canon_path), where=man["canonical"])

    mirror_rel = man.get("mirror")
    if mirror_rel:
        try:
            mirror = core_hash(_read(resolve(root, mirror_rel)), where=mirror_rel)
            if mirror != canon:
                problems.append(
                    f"MIRROR OUT OF SYNC: {mirror_rel} core {mirror[:12]} != "
                    f"{man['canonical']} core {canon[:12]}. Run --bump.")
        except CanonError as e:
            problems.append(f"MIRROR: {e}")

    for rel in man.get("pointers", []):
        try:
            text = _read(resolve(root, rel))
        except CanonError as e:
            problems.append(f"POINTER: {e}")
            continue
        m = STAMP.search(text)
        if not m:
            problems.append(
                f"POINTER MISSING STAMP: {rel} has no "
                f"'<!-- canon: <path> sha256:<64hex> -->' line")
            continue
        if CORE.search(text):
            problems.append(
                f"POINTER COPIES THE CANON: {rel} contains a CANON-CORE block. A "
                "pointer holds a delta, not a copy. Remove the block.")
        if m.group("sha") != canon:
            problems.append(
                f"POINTER STALE: {rel} declares {m.group('sha')[:12]}, canon is "
                f"{canon[:12]}. Re-read the canon, then --bump.")
    return problems


def bump(root: Path, manifest: "Path | None" = None) -> list[str]:
    man = load_manifest(manifest)
    canon_path = resolve(root, man["canonical"])
    canon_text = _read(canon_path)
    canon_block = CORE.search(canon_text).group(0)
    canon = core_hash(canon_text, where=man["canonical"])
    changed: list[str] = []

    mirror_rel = man.get("mirror")
    if mirror_rel:
        mp = resolve(root, mirror_rel)
        mt = _read(mp)
        new = CORE.sub(lambda _m: canon_block, mt, count=1)
        if new != mt:
            mp.write_text(new, encoding="utf-8")
            changed.append(f"re-synced mirror {mirror_rel}")

    for rel in man.get("pointers", []):
        p = resolve(root, rel)
        try:
            t = _read(p)
        except CanonError:
            continue
        stamp = f"<!-- canon: {man['canonical']} sha256:{canon} -->"
        if STAMP.search(t):
            new = STAMP.sub(stamp, t, count=1)
        else:
            new = stamp + "\n" + t
        if new != t:
            p.write_text(new, encoding="utf-8")
            changed.append(f"stamped {rel}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(REPO.parent),
                    help="workspace root the manifest paths resolve against")
    ap.add_argument("--manifest", default=None,
                    help="manifest to check; defaults to the public one. A PRIVATE "
                         "manifest (listing private repos) lives outside this public "
                         "repo and is passed here, so this repo never names them.")
    ap.add_argument("--bump", action="store_true",
                    help="re-sync the mirror and re-stamp pointers to the current canon")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    manifest = Path(args.manifest).resolve() if args.manifest else None

    try:
        if args.bump:
            for line in bump(root, manifest) or ["nothing to bump; already in sync"]:
                print(f"  {line}")
            print("instruction canon: bumped")
            return 0
        problems = verify(root, manifest)
    except CanonError as e:
        print(f"instruction canon: ERROR: {e}")
        return 1

    n = len(load_manifest(manifest).get("pointers", []))
    print(f"instruction canon: 1 canonical, 1 mirror, {n} pointer(s) checked")
    if problems:
        print("DRIFT:")
        for p in problems:
            print("  " + p)
        return 1
    print("every pointer matches the current canon: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
