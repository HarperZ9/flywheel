"""The release drafts for the lanes work say only what the evidence shows.

Three drafts go to the operator: the 1.0.4 known-issues correction (O-6), the
next release notes and the lane page. They are public once published, so the
two public-surface gates run on them here, although neither gate's file list
includes project-docs/drafts. Each lane's class is read from the committed
evidence summary of the installed-app acceptance, so a draft cannot state a
class the receipt did not measure, and the README lane-count sentence stays
as it is until the operator decides O-5.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import check_claim_language, check_public_instructions

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "project-docs" / "lanes" / "evidence" / "installed-lanes-local-20260926.json"
KNOWN_ISSUES = REPO / "project-docs" / "drafts" / "RELEASE-NOTES-1.0.4-known-issues.md"
NEXT_NOTES = REPO / "project-docs" / "drafts" / "RELEASE-NOTES-next.md"
LANE_PAGE = REPO / "project-docs" / "lanes" / "LANES.md"
DRAFTS = (KNOWN_ISSUES, NEXT_NOTES, LANE_PAGE)
CLASS_PAGES = (NEXT_NOTES, LANE_PAGE)
LABELS = {"BELOW_BAR": "below bar", "HELD": "not in this build"}
OVERCLAIMS = (
    re.compile(r"\bevery lane\b[^.\n]*\b(?:operational|runs|works)\b", re.I),
    re.compile(r"\ball (?:17|seventeen) lanes\b[^.\n]*\b(?:operational|run|work)", re.I),
    re.compile(r"\bfully operational\b", re.I),
)


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _label(row: dict) -> str:
    return row["class_measured"] if row["verdict"] == "AT_CLASS" else LABELS[row["verdict"]]


@pytest.mark.parametrize("path", DRAFTS, ids=lambda p: p.name)
def test_draft_passes_both_public_surface_gates(path):
    assert check_claim_language.scan(path) == []
    assert check_public_instructions.scan(path, REPO) == []


@pytest.mark.parametrize("path", DRAFTS, ids=lambda p: p.name)
def test_draft_is_plain_and_claims_no_lane_it_did_not_measure(path):
    text = path.read_text(encoding="utf-8")
    assert "—" not in text
    assert len(text.splitlines()) <= 300
    for rx in OVERCLAIMS:
        assert not rx.search(text), rx.pattern


@pytest.mark.parametrize("path", CLASS_PAGES, ids=lambda p: p.name)
def test_each_lane_row_states_its_measured_class(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for lane, row in _evidence()["lanes"].items():
        found = [line for line in lines if line.startswith(f"| {lane} |")]
        assert len(found) == 1, f"{path.name}: one table row for {lane}"
        cells = [cell.strip().lower() for cell in found[0].strip("|").split("|")]
        assert _label(row).lower() in cells, (lane, found[0])


def test_the_evidence_summary_counts_seventeen_lanes_and_names_its_limits():
    evidence = _evidence()
    assert len(evidence["lanes"]) == 17
    assert evidence["summary"]["verdict"] in {"PASS", "BELOW_BAR"}
    assert evidence["does_not_prove"]
    assert all(evidence["guards"].values())


def test_the_readme_lane_count_sentence_waits_for_the_operator():
    readme = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    assert ("About fifteen composable lanes ship in the roster, ten of them bundled "
            "natively from source.") in readme


def test_the_known_issues_draft_names_each_measured_1_0_4_gap():
    text = " ".join(KNOWN_ISSUES.read_text(encoding="utf-8").split())
    for token in ("level with a pip install", "env_allow", "forum", "exits",
                  "python -m harness.local_mcp", "status and doctor",
                  "articulate, calibrate-pro, learn and telos"):
        assert token in text, token
