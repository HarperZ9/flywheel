"""release_readiness.py -- 'every tool is release capable' as a receipt.

The maturity drive needs a stopping criterion that is measured, not felt.
This checks each tool in the family mechanically: repo present, the credo
placed, the belief section in the README, and tests present. Gaps are
named per tool; the summary counts ready over total; `all_ready` is the
condition the drive runs until. The checks are deliberately minimal and
extendable -- a bar that cannot be measured is not a bar.
"""
from __future__ import annotations

from pathlib import Path

SCHEMA = "flywheel.release-readiness/v1"

# The 14-flagship family; the platform's own two repos are added by name.
FAMILY = ("telos", "index", "forum", "gather", "crucible", "learn", "emet",
          "mneme", "plexus", "relay", "accountable-surface", "studio-engine",
          "proof-surface", "coherence-membrane")


def default_roots() -> dict:
    """Roots derived at call time — no path literals in shipped source
    (the run-paths gate enforces this). FLYWHEEL_FAMILY_ROOT overrides the
    lane parent; the default is the conventional layout relative to this
    checkout: <parent>/public/<lane>, with the desktop as a sibling."""
    import os
    here = Path(__file__).resolve().parents[1]
    public = Path(os.environ.get("FLYWHEEL_FAMILY_ROOT")
                  or here.parent / "public")
    roots = {name: str(public / name) for name in FAMILY}
    roots["flywheel-engine"] = str(here)
    roots["flywheel-desktop"] = str(here.parent / "flywheel-desktop")
    return roots


def _check(root: Path) -> list:
    gaps = []
    if not root.is_dir():
        return ["repo missing"]
    credo_path = root / "CREDO.md"
    if not credo_path.is_file():
        gaps.append("credo")
    else:
        # presence is not the check: the file must carry the canonical,
        # content-addressed credo text, or readiness can never go red on
        # a stale or reworded copy
        from .credo import CREDO
        try:
            credo_text = credo_path.read_text(encoding="utf-8",
                                              errors="ignore")
        except OSError:
            credo_text = ""
        if CREDO.strip() not in credo_text:
            gaps.append("credo drift")
    readme = root / "README.md"
    if not readme.is_file():
        gaps.append("readme")
    else:
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        if "What this believes" not in text:
            gaps.append("belief section")
    # A verification suite in any of its native shapes: pytest/dart test
    # dirs, a conformance runner over frozen vectors (emet's shape), or
    # node:test files (telos's shape), root-level or one directory deep.
    has_tests = (
        any((root / d).is_dir() and any((root / d).glob("*test*"))
            for d in ("tests", "test"))
        or (root / "conformance" / "run.py").is_file()
        or any(root.glob("*.test.mjs")) or any(root.glob("*.test.js"))
        or any(p for p in list(root.glob("*/*.test.mjs")) +
               list(root.glob("*/*.test.js"))
               if "node_modules" not in p.parts))
    if not has_tests:
        gaps.append("tests")
    return gaps


def readiness_report(roots: "dict | None" = None) -> dict:
    """Measure every tool. `roots` maps name -> path (defaults to the
    family roster); injectable so the falsifiers run on synthetic repos."""
    roots = roots if roots is not None else default_roots()
    tools = []
    for name in sorted(roots):
        gaps = _check(Path(roots[name]))
        tools.append({"name": name, "repo": str(roots[name]),
                      "gaps": gaps, "ready": not gaps})
    ready = sum(1 for t in tools if t["ready"])
    return {"schema": SCHEMA, "tools": tools,
            "ready_count": ready, "total": len(tools),
            "all_ready": ready == len(tools),
            "note": "mechanical bar: repo + credo + belief section + tests; "
                    "extend the bar rather than argue with it"}
