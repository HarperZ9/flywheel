"""Render the per-lane tables of the lane tool policy review from the table itself.

``project-docs/lanes/POLICY-REVIEW.md`` carries these tables between two marker
lines. ``--write`` replaces what sits between the markers; with no flag the
tables print to stdout. ``tests/test_lane_tool_policy.py`` fails when the
document's tables differ from a fresh render, so the review cannot drift from
``harness/lane_tool_policy.py``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.lane_tool_policy import (  # noqa: E402
    READS_ONLY_LANES, T2_EFFECTS, ToolPolicy, admitted_tools, lane_policy)
from harness.lanes_registry import LANES  # noqa: E402

START = "<!-- policy-tables:start (scripts/render_lane_policy_review.py) -->"
END = "<!-- policy-tables:end -->"
DEFAULT_DOC = ROOT / "project-docs" / "lanes" / "POLICY-REVIEW.md"


def _tier(entry: ToolPolicy) -> str:
    text = entry.tier
    if entry.tier == "T2" and entry.effect not in T2_EFFECTS:
        text += " (rule alone: T1)"
    if entry.not_in_build:
        text += f", not in build: `{entry.not_in_build}`"
    return text


def _forced(entry: ToolPolicy) -> str:
    parts = [f"drops `{name}`" if value is None else f"`{name}={str(value).lower()}`"
             for name, value in entry.forced_args]
    return ", ".join(parts)


def _row(name: str, entry: ToolPolicy) -> str:
    cells = (f"`{name}`", _tier(entry), "main" if entry.main else "", entry.effect,
             ", ".join(entry.needs), _forced(entry), entry.reason.replace("|", "/"))
    return "| " + " | ".join(cells) + " |"


def render_lane(lane: str) -> str:
    table = lane_policy(lane)
    t2 = sum(1 for e in table.values() if e.tier == "T2" and not e.not_in_build)
    out = sum(1 for e in table.values() if e.not_in_build)
    lines = [f"### {lane} {LANES[lane].version}", "",
             f"Admitted at launch: {len(admitted_tools(lane))} of {len(table)} tools. "
             f"T2 per granted call: {t2}. Not in this build: {out}."]
    if lane in READS_ONLY_LANES:
        lines.append(f"Reads only (class C): {READS_ONLY_LANES[lane]}")
    lines += ["", "| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |",
              "|---|---|---|---|---|---|---|"]
    lines += [_row(name, entry) for name, entry in table.items()]
    return "\n".join(lines)


def render_tables() -> str:
    """Every lane's table in registry order, between the two marker lines."""
    body = "\n\n".join(render_lane(lane) for lane in LANES)
    return f"{START}\n\n{body}\n\n{END}"


def write_tables(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _old, tail = rest.split(END, 1)
    path.write_text(head + render_tables() + tail, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", nargs="?", const=str(DEFAULT_DOC), default=None,
                        help="replace the tables in this document (default: the review)")
    args = parser.parse_args(argv)
    if args.write:
        write_tables(Path(args.write))
    else:
        sys.stdout.write(render_tables() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
