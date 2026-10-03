#!/usr/bin/env python3
"""check_private_lane_prose.py -- the private held lanes stay description-free.

The lanes in ``HELD_LANES`` (harness/lane_tool_policy.py) are private: they have
no freeze payload, do not launch on CI, and run only from a source checkout.
Their public-artifact fields must therefore carry no capability description,
only fixed neutral strings. This gate holds that invariant so a future edit
cannot quietly reintroduce descriptive prose on a public surface.

For every lane in ``HELD_LANES`` it checks four surfaces:
  (a) the registry role and organ (harness/lanes_registry.py) are the neutral
      constants;
  (b) the HELD_LANES card sentence is the neutral constant;
  (c) the desktop identity entry (desktop/lib/models/lane_identity.dart) carries
      only neutral fields (a bare title name plus the neutral identity/surface);
  (d) the feature doc (docs/features/lane-tool-policy.md) carries no descriptive
      line in the lane's section.

The gate names lanes only through ``HELD_LANES`` and holds no capability text,
so the gate file itself is public-safe. Exit 0 with a PASS line when clean; exit
1 listing the offending file and lane otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from harness.lane_tool_policy import HELD_LANES  # noqa: E402
from harness.lanes_registry import LANES  # noqa: E402

# The only strings a held lane's public fields may carry. Neutral by design.
NEUTRAL_ROLE = "Private lane; source checkout only."
NEUTRAL_ORGAN = "held"
NEUTRAL_CARD = "Private lane. Held out of this build; available only from a source checkout."
NEUTRAL_DART_IDENTITY = ("Private lane. Held out of this build; available only "
                         "from a source checkout.")
NEUTRAL_DART_SURFACE = "private lane"

DART_PATH = REPO / "desktop" / "lib" / "models" / "lane_identity.dart"
DOC_PATH = REPO / "docs" / "features" / "lane-tool-policy.md"


def check_registry(lane: str, entry) -> list[str]:
    """Role and organ for one held lane must be the neutral constants."""
    problems = []
    if getattr(entry, "role", None) != NEUTRAL_ROLE:
        problems.append(
            f"harness/lanes_registry.py [{lane}]: role is not the neutral constant")
    if getattr(entry, "organ", None) != NEUTRAL_ORGAN:
        problems.append(
            f"harness/lanes_registry.py [{lane}]: organ is not the neutral constant")
    return problems


def check_card(lane: str, sentence: str) -> list[str]:
    """The HELD_LANES card sentence must be the neutral constant."""
    if sentence != NEUTRAL_CARD:
        return [f"harness/lane_tool_policy.py [{lane}]: card sentence is not the "
                "neutral constant"]
    return []


def _dart_block(lane: str, text: str) -> str | None:
    m = re.search(r"'" + re.escape(lane) + r"':\s*LaneIdentity\((.*?)\),",
                  text, re.S)
    return m.group(1) if m else None


def check_dart(lane: str, text: str) -> list[str]:
    """The desktop identity entry must carry only neutral fields."""
    where = f"desktop/lib/models/lane_identity.dart [{lane}]"
    block = _dart_block(lane, text)
    if block is None:
        return [f"{where}: no LaneIdentity entry found"]
    title_m = re.search(r"title:\s*'([^']*)'", block)
    if not title_m or not re.fullmatch(r"[A-Za-z0-9]+", title_m.group(1)) \
            or title_m.group(1).lower() != lane.lower():
        return [f"{where}: title is not the bare lane name"]
    # Split the value regions and require exactly one neutral literal in each.
    id_region = block.split("identity:", 1)[-1].split("surface:", 1)[0]
    sf_region = block.split("surface:", 1)[-1]
    id_lits = re.findall(r"'([^']*)'", id_region)
    sf_lits = re.findall(r"'([^']*)'", sf_region)
    problems = []
    if id_lits != [NEUTRAL_DART_IDENTITY]:
        problems.append(f"{where}: identity is not the neutral constant")
    if sf_lits != [NEUTRAL_DART_SURFACE]:
        problems.append(f"{where}: surface is not the neutral constant")
    return problems


def check_doc(lane: str, text: str) -> list[str]:
    """The feature-doc section for a held lane must carry no descriptive line."""
    where = f"docs/features/lane-tool-policy.md [{lane}]"
    sections = list(re.finditer(r"^###\s+" + re.escape(lane)
                                + r"\b.*?(?=^###\s|^<!-- policy-tables:end -->\s*$|\Z)",
                                text, re.S | re.M))
    if not sections:
        # No section for the lane is fine: nothing to describe it.
        return []
    if len(sections) != 1:
        return [f"{where}: duplicate lane sections"]
    lines = [line.strip() for line in sections[0].group(0).splitlines() if line.strip()]
    expected_body = [
        "Admitted at launch: 0 of 0 tools. T2 per granted call: 0. Not in this build: 0.",
        "| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    if (not re.fullmatch(r"### " + re.escape(lane) + r" \d+\.\d+\.\d+", lines[0])
            or lines[1:] != expected_body):
        return [f"{where}: section is not the neutral empty tool table"]
    return []


def run_checks(held_lanes, registry, dart_text: str, doc_text: str) -> list[str]:
    """Every problem across all held lanes, as short messages; empty when clean."""
    problems: list[str] = []
    for lane, sentence in held_lanes.items():
        entry = registry.get(lane)
        if entry is None:
            problems.append(f"harness/lanes_registry.py [{lane}]: no registry entry")
        else:
            problems.extend(check_registry(lane, entry))
        problems.extend(check_card(lane, sentence))
        problems.extend(check_dart(lane, dart_text))
        problems.extend(check_doc(lane, doc_text))
    return problems


def main() -> int:
    dart_text = DART_PATH.read_text(encoding="utf-8")
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    problems = run_checks(HELD_LANES, LANES, dart_text, doc_text)
    if problems:
        print("PRIVATE LANE PROSE GATE FAILED:")
        for p in problems:
            print("  " + p)
        print("\nA held lane's public fields must carry only the fixed neutral "
              "strings. Restore them or update this gate's neutral constants.")
        return 1
    print(f"PASS: {len(HELD_LANES)} held lane(s) carry only neutral fields "
          "on every checked public surface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
