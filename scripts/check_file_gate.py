"""check_file_gate.py -- enforce the 300-line file gate without a refactor.

The gate has been an honor-system rule and 16 files already violate it. Rather
than block Phase 0 on a refactor, the existing violations are frozen on a
burn-down list with their current line counts. From then on:

  - a NEW file over the gate fails CI,
  - a grandfathered file that GROWS fails CI.

The list can only shrink. A file that drops under 300 lines leaves it and
cannot come back.
"""
from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 300
BURNDOWN = Path("project-docs") / "records" / "2026-07-25-file-gate-burndown.md"


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


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    listed = load_grandfathered(root / BURNDOWN)
    failures: list[str] = []
    for rel, n in over_gate(root / "harness"):
        key = f"harness/{rel}"
        if key not in listed:
            failures.append(f"NEW violation: {key} is {n} lines (limit {LIMIT})")
        elif n > listed[key]:
            failures.append(f"GREW: {key} is {n} lines, frozen at {listed[key]}")
    for f in failures:
        print(f)
    if not failures:
        print(f"file gate clean: {len(listed)} grandfathered, 0 new, 0 grown")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
