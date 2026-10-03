"""The crucible 1.3.0 pin, which closes GHSA-49qx-cj4f-wfqv.

crucible-bench 1.2.0 and earlier decide MATCH or DRIFT from the measurement
row's tolerance, which no seal covers, so a measurement file could widen it and
every later check agreed; their status and doctor answered MATCH without
measuring anything. 1.3.0 lets a claim seal its tolerance, answers OK from
status and doctor, and adds one MCP tool, ``crucible.recheck_template``, which
reads a registry assessment and returns a replay template. The tool writes
nothing, so the policy lists it as a T1 read with its path arguments kept out of
the Flywheel home, as ``crucible.report``'s are.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness import lane_tool_policy as policy
from harness.lane_tier_gate import argument_refusal
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
VERSION, TAG, COMMIT = "1.4.0", "v1.4.0", "f06b8d1d06ad0c9a3ff31de3fda1a2fa7fe036de"
ADVISORY = "GHSA-49qx-cj4f-wfqv"
NEW_TOOL = "crucible.recheck_template"


def _text(*parts: str) -> str:
    return " ".join(ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


def test_registry_and_row_carry_the_pin():
    row = ROWS["crucible"]
    assert LANES["crucible"].version == VERSION
    assert (row["owner_tag"], row["owner_describe"], row["owner_commit"]) == (TAG, TAG, COMMIT)
    assert row["flywheel_registry_expected_version"] == VERSION
    assert row["owner_project"]["version"] == VERSION
    assert row["owner_project"]["imported_version"] == VERSION
    assert row["owner_project"]["license"] == "LicenseRef-FSL-1.1-MIT"
    assert row["component_descriptor"]["version"] == VERSION
    assert row["component_descriptor"]["source"]["commit"] == COMMIT


def test_the_new_tool_has_a_reviewed_row_and_every_served_tool_is_listed():
    row = ROWS["crucible"]
    served = row["mcp"]["static_tool_names"]
    assert NEW_TOOL in served and len(served) == 14
    assert set(served) == set(policy.lane_policy("crucible"))
    entry = policy.tool_policy("crucible", NEW_TOOL)
    assert (entry.tier, entry.effect, entry.not_in_build) == ("T1", "read", "")
    assert entry.path_args == ("dir", "index")
    assert NEW_TOOL in policy.admitted_tools("crucible")
    assert row["component_descriptor"]["allowed_tools"] == policy.admitted_tools("crucible")


def test_the_new_tool_keeps_its_registry_out_of_the_flywheel_home(tmp_path):
    home = tmp_path / "home"
    (home / "lanes" / "crucible").mkdir(parents=True)
    environ = {"FLYWHEEL_HOME": str(home)}
    refused = argument_refusal("crucible", NEW_TOOL, {"dir": str(home / "keys")}, environ)
    assert refused is not None and refused["reason"] == "argument_refused"
    own = home / "lanes" / "crucible" / "registry"
    assert argument_refusal("crucible", NEW_TOOL, {"dir": str(own)}, environ) is None


def test_the_notice_names_the_tag_and_drops_the_old_release():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    assert (f"crucible-bench {VERSION} (lane crucible), tag {TAG} @ {COMMIT[:12]}, "
            "LicenseRef-FSL-1.1-MIT") in text
    assert "crucible-bench 1.2.0 (lane crucible)" not in text


def test_the_notes_and_the_known_issues_page_name_the_advisory():
    notes = _text("RELEASE-NOTES-1.1.0.md")
    fixes = notes.split("Security fixes in the lanes", 1)[1].split("## ", 1)[0]
    assert f"crucible 1.3.0 fixes {ADVISORY}" in fixes
    assert "crucible 1.2.0, which 1.0.4 pins" in fixes
    assert f"`{NEW_TOOL}`" in notes.split("**Lane updates.**", 1)[1].split("- **", 1)[0]
    assert "None adds a tool" not in notes
    known = _text("RELEASE-NOTES-1.0.4-known-issues.md")
    assert f"crucible 1.2.0, which 1.0.4 pins, is inside the range of {ADVISORY}" in known


def test_the_feature_page_describes_the_pinned_release():
    page = _text("docs", "features", "crucible.md")
    assert "14 tools" in page and "13 tools" not in page and "Thirteen tools" not in page
    assert f"`{NEW_TOOL}`" in page
    assert "**Sealed-tolerance defense (1.3.0).**" in page
    assert ADVISORY in page
    assert "Crucible sits at tier T1" not in page
