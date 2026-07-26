#!/usr/bin/env python3
"""check_public_instructions.py -- a public instruction file must stand alone.

Wave 2 of the instruction-canon rollout turned up a design fact worth stating:
the public repos under `public/` are published and cloned on their own, so they
are NOT part of the local canon. A pointer that said "inherited from
c:/dev/CLAUDE.md" would be a local path on a public surface AND false for a
standalone clone. Public repos are self-contained by necessity.

So the invariant this gate holds is not "matches the canon" but "leaks nothing
local": a public instruction file names no local path and no internal project.
It complements `check_claim_language.py` (which governs public PROSE) and
`check_instruction_canon.py` (which governs INTERNAL pointer drift). Together
they are the three registers: internal single-source, public self-containment,
and no over-claim on either.

Exit 0 clean, 1 with leaks listed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO.parent               # the workspace root, parent of local-model

# Public repos that do NOT live under public/. Wave 3 of the instruction-canon
# rollout found two: state/emet and state/behavior-transform.io are PUBLIC on
# GitHub (verified via `gh repo view` 2026-07-26: emet PUBLIC,
# behavior-transform.io PUBLIC) while sitting under state/. A gate that scanned
# only public/ would leave them unguarded, which is exactly the blind spot a
# published-surface check exists to close. Visibility, not directory, is what
# makes a repo public; this list carries the ones convention misfiles.
EXTRA_PUBLIC = (
    "local-model",                       # this repo is public; scan its own files
    "state/emet",
    "state/behavior-transform.io",
)

# GENERIC leaks a public instruction file must not carry: a local drive path or
# a reference to a parent workspace that will not exist on a standalone clone.
# These are patterns, not private names, so this list is itself public-safe.
LEAKS = [
    (r"[A-Za-z]:[\\/](?:dev|Users)\b", "a local drive path"),
    (r"/(?:c|e)/(?:dev|local-model|Users)\b", "a local drive path"),
    (r"\b[A-Za-z]:[\\/]local-model-run\b", "a local run-drive path"),
    (r"\bworkspace root\b", "the workspace root (absent from a standalone clone)"),
    (r"\binherited from the parent\b", "a parent that will not exist on clone"),
]

# Private PROJECT NAMES are deliberately NOT listed in this public file (naming
# them here would itself be the leak). The operator keeps them in a gitignored
# denylist, one regex per line, loaded only when present. In CI or a clone the
# file is absent and the gate runs on the generic patterns alone.
_DENYLIST = Path(__file__).resolve().parent / ".private-denylist.txt"


def _load_rules() -> list:
    rules = [(re.compile(p), why) for p, why in LEAKS]
    if _DENYLIST.is_file():
        for line in _DENYLIST.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rules.append((re.compile(line), "a private project name (denylist)"))
    return rules


_RX = _load_rules()


def public_files(root: Path) -> list[Path]:
    names = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
    out: dict = {}
    pub = root / "public"
    if pub.is_dir():
        for name in names:
            # depth <= 2 under public/, skipping caches
            for p in list(pub.glob(name)) + list(pub.glob("*/" + name)):
                if ".ruff_cache" in p.parts or ".telos" in p.parts:
                    continue
                out[p.resolve()] = p
    # public repos that live elsewhere (verified public via gh, see EXTRA_PUBLIC)
    for rel in EXTRA_PUBLIC:
        d = root / rel
        for name in names:
            p = d / name
            if p.is_file():
                out[p.resolve()] = p
    return sorted(out.values())


def scan(path: Path, root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(root).as_posix()
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for rx, why in _RX:
            m = rx.search(line)
            if m:
                hits.append(f"{rel}:{i} names {m.group(0)!r} ({why})")
    return hits


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()

    files = public_files(root)
    leaks: list[str] = []
    for f in files:
        leaks.extend(scan(f, root))
    print(f"public instruction hygiene: scanned {len(files)} published "
          f"instruction file(s) (public/ plus {len(EXTRA_PUBLIC)} elsewhere)")
    if not files:
        print("  no published instruction files found at this root")
    if leaks:
        print("A PUBLIC INSTRUCTION FILE LEAKS A LOCAL OR INTERNAL REFERENCE:")
        for x in leaks:
            print("  " + x)
        print("\nA published repo is cloned on its own. Its instructions must "
              "stand alone: no local path, no internal project name.")
        return 1
    print("every public instruction file stands alone: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
