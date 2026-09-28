"""The release pages for the lanes work say only what the evidence shows.

Three pages carry the lane claims: the 1.0.4 known-issues correction, the 1.1.0
release notes and the lane page. They are public, so the two public-surface
gates run on them here, although neither gate's file list names them. Each
lane's class is read from the committed evidence summary of the installed-app
acceptance, so a page cannot state a class the receipt did not measure, and the
README lane sentence carries the receipt's own count: public lane wording comes
only from the receipt. scripts/make_installed_lanes_evidence.py writes the
summary from a run's artifact, and its --update-copy moves EVIDENCE and the
run, commit and installer size the pages name.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import check_claim_language, check_data_location_copy, check_public_instructions

REPO = Path(__file__).resolve().parents[1]
# The CI run both legs of which the notes and the lane page count from: the
# installed-app acceptance run on the release source commit.
EVIDENCE = (REPO / "project-docs" / "lanes" / "evidence"
            / "installed-lanes-ci-36302181098.json")
KNOWN_ISSUES = REPO / "RELEASE-NOTES-1.0.4-known-issues.md"
NEXT_NOTES = REPO / "RELEASE-NOTES-1.1.0.md"
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
    # The notes pages sit at the repository root, inside the data-location
    # gate's surface list; the lane page is outside it, so check all three here.
    text = path.read_text(encoding="utf-8")
    assert check_data_location_copy.violations_in(text, path.name) == []


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
    assert {leg["install_mode"] for leg in evidence["legs"].values()} == {
        "per-user", "all-users"}


@pytest.mark.parametrize("path", CLASS_PAGES, ids=lambda p: p.name)
def test_the_copy_names_the_run_and_commit_its_classes_come_from(path):
    text = " ".join(path.read_text(encoding="utf-8").split())
    evidence = _evidence()
    assert f"run {evidence['run']['run_id']}" in text
    assert evidence["source_commit"][:8] in text


def test_the_readme_lane_sentence_carries_the_receipt_count():
    readme = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    lanes = _evidence()["lanes"]
    at_class = sum(1 for row in lanes.values() if row["verdict"] == "AT_CLASS")
    sentence = (f"In the Windows app's installed-app check, {at_class} of {len(lanes)} "
                "lanes reach the class the check expects for them")
    assert sentence in readme
    assert "About fifteen composable lanes" not in readme
    assert "the class their card states" not in readme
    notes = " ".join(NEXT_NOTES.read_text(encoding="utf-8").split())
    assert sentence in notes


def test_the_known_issues_draft_names_each_measured_1_0_4_gap():
    text = " ".join(KNOWN_ISSUES.read_text(encoding="utf-8").split())
    for token in ("level with a pip install", "env_allow", "forum", "exits",
                  "python -m harness.local_mcp", "status and doctor",
                  "articulate, calibrate-pro, learn and telos"):
        assert token in text, token


def test_the_notes_class_breakdown_is_the_receipts_count_per_class():
    """The per-class clause follows the receipt's summary.by_class, so the
    summary that replaces EVIDENCE cannot leave stale counts behind."""
    notes = " ".join(NEXT_NOTES.read_text(encoding="utf-8").split())
    start = notes.index("lanes reach the class the check expects for them:")
    clause = notes[start:notes.index(". ", start)]
    found = {cls: int(n) for n, cls in re.findall(r"(\d+) [^,()]*?\(([^()]+)\)", clause)}
    assert found == _evidence()["summary"]["by_class"]


@pytest.mark.parametrize("path", CLASS_PAGES, ids=lambda p: p.name)
def test_the_copy_keeps_where_the_lane_check_ran(path):
    """The receipt's first does_not_prove says where the run ran: a Windows
    Server runner, an administrator account, the network reachable and no host
    model server. The notes and the lane page keep each part, so a reader does
    not take the classes as measured offline or on a consumer machine."""
    text = " ".join(path.read_text(encoding="utf-8").split()).lower()
    limit = _evidence()["does_not_prove"][0].lower()
    for part in ("windows server", "administrator", "network", "reachable",
                 "no host model server"):
        assert part in limit, part
        assert part in text, (path.name, part)
