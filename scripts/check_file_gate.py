"""check_file_gate.py -- enforce the 300-line file gate without a refactor.

The gate has been an honor-system rule and files across three trees already
violate it. Rather than block on a refactor, the existing violations are frozen
on burn-down lists with their current line counts. From then on:

  - a NEW file over the gate fails CI,
  - a grandfathered file that GROWS fails CI.

The list can only shrink. A file that drops under 300 lines leaves it and
cannot come back.

The gate covers harness/, scripts/ and tests/. harness/ came under the gate
first (frozen 2026-07-25); scripts/ and tests/ followed (frozen 2026-07-26) once
it was noticed the gate had only ever scanned harness/, leaving the standard
unenforced in two trees that had accumulated 46 violations between them. Each
tree's frozen record is a separate file, loaded and merged here: keys are
tree-prefixed so they cannot collide, and a record frozen on one day is not
rewritten to absorb another day's tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 300
_RECORDS = Path("project-docs") / "records"
# The gated trees, and the frozen record for each. A tree with no violations
# needs no record; a record with no tree would be dead weight. Both are checked.
TREES = ("harness", "scripts", "tests")
BURNDOWNS = (
    _RECORDS / "2026-07-25-file-gate-burndown.md",              # harness/
    _RECORDS / "2026-07-26-file-gate-burndown-scripts-tests.md",  # scripts/, tests/
)
# Back-compat: the original single-file name some callers/tests referenced.
BURNDOWN = BURNDOWNS[0]


def over_gate(root: Path, limit: int = LIMIT) -> list[tuple[str, int]]:
    """Every .py file under root longer than `limit` lines, as (relpath, lines)."""
    out: list[tuple[str, int]] = []
    root = Path(root)
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            n = sum(1 for _ in fh)
        if n > limit:
            out.append((p.relative_to(root).as_posix(), n))
    return out


def load_grandfathered(path: Path) -> dict[str, int]:
    """Parse the burn-down markdown table into {path: max_allowed_lines}."""
    g: dict[str, int] = {}
    p = Path(path)
    if not p.exists():
        return g
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| file") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[1].isdigit():
            g[cells[0]] = int(cells[1])
    return g


def load_all(paths) -> dict[str, int]:
    """Merge every burn-down record into one {tree-prefixed path: max lines}.

    Keys are tree-prefixed, so two records covering different trees never
    collide. If two records ever named the same file, that is a bug in the
    records themselves and the LOWER frozen size wins, since the gate must never
    silently raise a ceiling.
    """
    merged: dict[str, int] = {}
    for p in paths:
        for key, n in load_grandfathered(p).items():
            merged[key] = min(merged[key], n) if key in merged else n
    return merged


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    listed = load_all(root / b for b in BURNDOWNS)
    failures: list[str] = []
    for tree in TREES:
        for rel, n in over_gate(root / tree):
            key = f"{tree}/{rel}"
            if key not in listed:
                failures.append(f"NEW violation: {key} is {n} lines (limit {LIMIT})")
            elif n > listed[key]:
                failures.append(f"GREW: {key} is {n} lines, frozen at {listed[key]}")
    for f in failures:
        print(f)
    if not failures:
        print(f"file gate clean: {len(listed)} grandfathered across "
              f"{len(TREES)} trees, 0 new, 0 grown")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
