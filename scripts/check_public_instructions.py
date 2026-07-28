#!/usr/bin/env python3
"""check_public_instructions.py -- a public instruction file must stand alone.

The design fact this gate was built on: every project here is its own repo,
published and cloned on its own, so no project's instructions can point at the
c:/dev workspace canon. A reference like "inherited from c:/dev/CLAUDE.md" would
be a local path on a public surface AND false for a standalone clone. Public
repos are self-contained by necessity.

So the invariant this gate holds is "leaks nothing local": a public instruction
file names no local path and no internal project. It complements
`check_claim_language.py` (which governs public PROSE); the workspace canon at
c:/dev is inherited only by a session rooted there, never pointed at from a repo.

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
# This repo is NOT listed here. It is scanned by path as REPO, always, because
# naming it "local-model" only found it when the checkout happened to carry that
# directory name: from a worktree the entry resolved to a DIFFERENT checkout of
# the same repo, so the gate scanned somebody else's branch and reported on it.
EXTRA_PUBLIC = (
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

# The checkout this gate ships in, scanned by PATH and never by directory
# name. Named "local-model" it was found only when the directory happened to
# carry that name; from a worktree the entry resolved to a different checkout
# and the tree being gated went unscanned while the gate reported clean.
EXTRA_ROOTS = (REPO,)


# PUBLISHED PRODUCT SURFACES, scanned with the same rules as the instruction
# files above. Widened after a model card carrying a build-machine path
# (`E:\...\telos-coder-32b-cpt2019-q4_k_m.gguf`) reached a branch and was caught
# by hand rather than by this gate. The machinery was already here; only the
# file selection was too narrow, and a gate that reads three filenames cannot
# see the surface a stranger actually reads first.
#
# The rule these hold is the canon's: internal register docs may carry local
# paths, published surfaces may not. So this scans releases, cards and READMEs,
# and deliberately NOT project-docs/records, plans or specs.
SURFACE_GLOBS = (
    "README.md",
    "MODEL_CARD.md",
    "project-docs/releases/*/*.md",
    "project-docs/releases/*.md",
)


# Widening this gate found 33 pre-existing leaks across surfaces that had never
# been scanned. Blocking on 33 doc rewrites would have meant leaving the gate
# off, which is how the model card regression got in. So the same mechanism
# check_file_gate.py already uses applies here: freeze the existing violations
# with their counts, fail a NEW one, fail a GROWN one, and let the list only
# shrink. The gate protects from today forward while the debt burns down.
SURFACE_BURNDOWN = (Path("project-docs") / "records"
                    / "2026-07-28-public-surface-burndown.md")
_BURNDOWN_RX = re.compile(r"^-\s+`([^`]+)`\s+[-=]\s+(\d+)\s*$")


def load_burndown(repo: Path) -> dict:
    """path -> frozen leak count. An absent record means nothing is grandfathered,
    which is the correct reading for a fresh clone rather than a reason to skip."""
    p = repo / SURFACE_BURNDOWN
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = _BURNDOWN_RX.match(line.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def _load_rules() -> list:
    rules = [(re.compile(p), why) for p, why in LEAKS]
    if _DENYLIST.is_file():
        for line in _DENYLIST.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rules.append((re.compile(line), "a private project name (denylist)"))
    return rules


_RX = _load_rules()


def public_files(root: Path, extra_roots=None) -> list[Path]:
    """Instruction files under `root`, plus `extra_roots` (this checkout by
    default). The extra roots are a PARAMETER rather than a hidden constant so
    the function still answers honestly for the root it was handed, which is
    what makes it testable against a synthetic tree."""
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
    # THIS repo by path, plus the public repos that live elsewhere (verified
    # public via gh, see EXTRA_PUBLIC). REPO is listed by path rather than by
    # directory name for the reason given above EXTRA_PUBLIC.
    roots = list(EXTRA_ROOTS if extra_roots is None else extra_roots)
    for d in roots + [root / rel for rel in EXTRA_PUBLIC]:
        for name in names:
            p = d / name
            if p.is_file():
                out[p.resolve()] = p
    return sorted(out.values())


def published_surface_files(root: Path, extra_roots=None) -> list[Path]:
    """The pages a stranger reads first, inside every public repo.

    Same repos as `public_files`, different filenames: a model card and a usage
    page are product surfaces even though neither is an instruction file.
    """
    # REPO first, and by path rather than by name. EXTRA_PUBLIC names this repo
    # "local-model", which is the directory it usually sits in and not the
    # directory it always sits in: from a git worktree, or a CI runner that
    # checks out elsewhere, that entry resolves to somebody else's files while
    # the checkout being gated goes unscanned. A gate that misses the tree it
    # ships in is worse than no gate, because it reports clean.
    roots = list(EXTRA_ROOTS if extra_roots is None else extra_roots)
    roots += [root / rel for rel in EXTRA_PUBLIC]
    pub = root / "public"
    if pub.is_dir():
        roots.extend(p for p in pub.iterdir() if p.is_dir())
    out: dict = {}
    for base in roots:
        if not base.is_dir():
            continue
        for pattern in SURFACE_GLOBS:
            for p in base.glob(pattern):
                if not p.is_file() or ".ruff_cache" in p.parts or ".telos" in p.parts:
                    continue
                out[p.resolve()] = p
    return sorted(out.values())


def classify_surfaces(per_file: dict, frozen: dict):
    """The burn-down decision, as a pure function: (new, grown, shrunk, failures).

    Lifted out of main() because it was the part with the rules in it and the
    part no test could reach. Deleting the new-surface branch or the growth
    branch left every test green while the gate stopped gating.
    """
    new, grown, shrunk, failures = [], [], [], []
    for path, hits in sorted(per_file.items()):
        was = frozen.get(path)
        if was is None:
            new.append(f"{path}: {len(hits)} leak(s) on a surface that was clean")
            failures.extend(hits)
        elif len(hits) > was:
            grown.append(f"{path}: {len(hits)} leak(s), frozen at {was}")
            failures.extend(hits)
        elif len(hits) < was:
            shrunk.append(f"{path}: {len(hits)} leak(s), down from {was}")
    for path, was in sorted(frozen.items()):
        if path not in per_file and was:
            shrunk.append(f"{path}: clean now, was {was}")
    return new, grown, shrunk, failures


def key_for(path: Path, root: Path) -> str:
    """The ONE name a file is known by, here and in the burn-down record.

    A file inside THIS repo is keyed repo-relative, never workspace-relative, so
    an entry written from one checkout matches the same file read from a
    worktree, a CI runner, or a fresh clone. Files in OTHER public repos keep
    their workspace-relative path, which is the only name they have from here.

    One function because two call sites computing this separately is exactly how
    the reporting and the burn-down came to disagree about the same file.
    """
    if path.resolve().is_relative_to(REPO.resolve()):
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    return path.relative_to(root).as_posix()


def scan(path: Path, root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = key_for(path, root)
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
    surfaces = published_surface_files(root)
    frozen = load_burndown(REPO)

    per_file: dict = {}
    instruction_leaks: list[str] = []
    for f in files:
        instruction_leaks.extend(scan(f, root))
    for f in surfaces:
        hits = scan(f, root)
        if hits:
            per_file[key_for(f, root)] = hits

    print(f"public hygiene: scanned {len(files)} instruction file(s) "
          f"(public/ plus {len(EXTRA_PUBLIC)} elsewhere) and "
          f"{len(surfaces)} published surface(s); "
          f"{len(frozen)} surface(s) grandfathered")

    # Instruction files were never grandfathered and are not now: that gate has
    # been clean since it went on, and a burn-down for a clean rule is only a
    # way to make it dirty again.
    new, grown, shrunk, surface_failures = classify_surfaces(per_file, frozen)
    failures = list(instruction_leaks) + surface_failures

    for line in shrunk:
        print("  burned down: " + line)
    if not failures:
        print("no new leak on any published instruction file or surface")
        if shrunk:
            print("  the burn-down record can be lowered to match")
        return 0
    print("A PUBLISHED FILE LEAKS A LOCAL OR INTERNAL REFERENCE:")
    for x in new + grown:
        print("  " + x)
    for x in failures:
        print("    " + x)
    print("\nA published repo is cloned on its own, and its surfaces are read "
          "by strangers. No local path, no internal project name. Internal "
          "register docs under project-docs/records, plans and specs are exempt "
          "by design and are not scanned here.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
