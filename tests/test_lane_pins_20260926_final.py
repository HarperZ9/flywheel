"""The final 2026-09-26 pins: mneme 0.5.1 and canon 0.4.2.

Both close published advisories in the releases the late pins named:

- mneme 0.5.1 closes GHSA-j2pw-g7f4-9ppp (0.5.0's forget could keep erased
  text in its reason, erase another user's turn, and confirm a guess through
  the receipt's plan digest);
- canon 0.4.2 closes GHSA-48rq-xjfx-6j4f (0.4.1 stored an MCP ingest
  unredacted, cut query excerpts before scrubbing, returned pending references
  unscrubbed and put transcript paths into the next prompt).

Every pin site agrees, and neither release adds a lane server tool, so the
policy table keeps its rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
PINS = {"mneme": ("0.6.0", "v0.6.0", "fc7097e38f20724dceb6b804a2e722f65236b2ec"),
        "canon": ("0.6.0", "v0.6.0", "c3ff3cd322657d37cb095d0d619a4119e0b964fd")}
ADVISORIES = {"mneme": "GHSA-j2pw-g7f4-9ppp", "canon": "GHSA-48rq-xjfx-6j4f"}


@pytest.mark.parametrize("lane", sorted(PINS))
def test_registry_and_row_carry_the_final_pin(lane):
    version, tag, commit = PINS[lane]
    row = ROWS[lane]
    assert LANES[lane].version == version
    assert (row["owner_tag"], row["owner_commit"]) == (tag, commit)
    assert row["flywheel_registry_expected_version"] == version
    assert row["owner_project"]["version"] == version
    assert row["component_descriptor"]["version"] == version


@pytest.mark.parametrize("lane", sorted(PINS))
def test_no_new_lane_tool_enters_with_the_pin(lane):
    served = set(ROWS[lane]["component_descriptor"]["allowed_tools"])
    assert served == set(policy.admitted_tools(lane))


def test_the_notices_name_each_final_pin():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    for lane, (version, tag, commit) in PINS.items():
        assert f"{ROWS[lane]['registry_install_name']} {version} (lane {lane}), tag {tag} " \
               f"@ {commit[:12]}" in text
    assert "flywheel-mneme 0.5.0" not in text and "flywheel-canon 0.4.1" not in text


def test_the_canon_context_checks_name_the_final_pin():
    from scripts import check_installed_canon_context as installed
    assert installed.CANON_PIN == PINS["canon"][2]
    source = (ROOT / "scripts" / "check_frozen_gateway.py").read_text(encoding="utf-8")
    assert PINS["canon"][2] in source and PINS["canon"][2] == ROWS["canon"]["owner_commit"]


def test_the_release_notes_name_both_advisories_as_fixed():
    notes = (ROOT / "RELEASE-NOTES-1.1.0.md").read_text(
        encoding="utf-8")
    fixes = notes.split("Security fixes in the lanes", 1)[1].split("\n## ", 1)[0]
    for lane, advisory in ADVISORIES.items():
        assert advisory in fixes, lane
    assert "mneme 0.5.1" in notes and "canon 0.4.2" in notes
    assert "mneme 0.5.0 and canon 0.4.1" not in notes
