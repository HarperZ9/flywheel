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

# The 14-flagship family plus the platform's own two repos.
DEFAULT_ROOTS = {
    "telos": "C:/dev/public/telos",
    "index": "C:/dev/public/index",
    "forum": "C:/dev/public/forum",
    "gather": "C:/dev/public/gather",
    "crucible": "C:/dev/public/crucible",
    "learn": "C:/dev/public/learn",
    "emet": "C:/dev/public/emet",
    "mneme": "C:/dev/public/mneme",
    "plexus": "C:/dev/public/plexus",
    "relay": "C:/dev/public/relay",
    "accountable-surface": "C:/dev/public/accountable-surface",
    "studio-engine": "C:/dev/public/studio-engine",
    "proof-surface": "C:/dev/public/proof-surface",
    "coherence-membrane": "C:/dev/public/coherence-membrane",
    "flywheel-engine": "C:/dev/local-model",
    "flywheel-desktop": "C:/dev/flywheel-desktop",
}


def _check(root: Path) -> list:
    gaps = []
    if not root.is_dir():
        return ["repo missing"]
    if not (root / "CREDO.md").is_file():
        gaps.append("credo")
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
    # dirs, or a conformance runner over frozen vectors (emet's shape).
    has_tests = any(
        (root / d).is_dir() and any((root / d).glob("*test*"))
        for d in ("tests", "test")) or (root / "conformance" / "run.py").is_file()
    if not has_tests:
        gaps.append("tests")
    return gaps


def readiness_report(roots: "dict | None" = None) -> dict:
    """Measure every tool. `roots` maps name -> path (defaults to the
    family roster); injectable so the falsifiers run on synthetic repos."""
    roots = roots if roots is not None else DEFAULT_ROOTS
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
