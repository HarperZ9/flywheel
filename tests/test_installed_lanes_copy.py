"""The release copy moves onto a new evidence summary only by its known phrases.

scripts/installed_lanes_copy.py rewrites the run id, short commit, run date and
installer size in the notes and the lane page, and the summary name in the
drafts test. These tests hold it to three rules: it keeps each phrase's own
line breaks, it writes nothing when a phrase is missing or doubled, and it
refuses a run whose lanes differ from the summary the copy was written from.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import installed_lanes_copy as lc

REPO = Path(__file__).resolve().parents[1]
SENTENCE = "In the check, 1 of 1 lanes reach the class the check expects for them."
NOTES = (f"{SENTENCE}\r\nMeasured by a check (CI run 111, commit aaaaaaaa)\r\nthat installs.\r\n"
         "The installer is about 0.5 MB larger, mostly Node: 1,500,000\r\nbytes in CI run "
         "111 against 1,000,000 bytes for 1.0.4.\r\n")
LANES = ("The classes come from CI run 111 on 2026-01-01 against commit aaaaaaaa,\n"
         "summarized in `evidence/installed-lanes-ci-111.json`; both legs.\n")
TEST = 'EVIDENCE = (REPO / "x"\n            / "installed-lanes-ci-111.json")\n'


def _evidence(run: int, commit: str, date: str, size: int) -> dict:
    return {"run": {"run_id": run, "date": date}, "source_commit": commit,
            "installer": {"bytes": size},
            "lanes": {"gather": {"verdict": "AT_CLASS", "class_measured": "A"}}}


OLD = _evidence(111, "a" * 40, "2026-01-01", 1_500_000)
NEW = _evidence(222, "b" * 40, "2026-02-02", 2_750_000)


def _repo(tmp_path: Path, notes: str = NOTES) -> Path:
    for rel, text in ((lc.TEST, TEST), (lc.NOTES, notes), (lc.LANE_PAGE, LANES),
                      (lc.README, SENTENCE + "\n")):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(text.encode("utf-8"))
    return tmp_path


def _read(root: Path, rel: Path) -> str:
    return (root / rel).read_bytes().decode("utf-8")


def test_each_phrase_moves_and_keeps_its_line_breaks(tmp_path):
    root = _repo(tmp_path)
    assert lc.current_evidence(root) == "installed-lanes-ci-111.json"
    lines = lc.apply(root, lc.plan(root, OLD, NEW, "installed-lanes-ci-222.json"))
    assert len(lines) == 3
    notes = _read(root, lc.NOTES)
    assert "(CI run 222, commit bbbbbbbb)\r\n" in notes
    assert "about 1.8 MB larger" in notes
    assert "2,750,000\r\nbytes in CI run 222 against 1,000,000 bytes" in notes
    assert "111" not in notes and "aaaaaaaa" not in notes
    page = _read(root, lc.LANE_PAGE)
    assert "CI run 222 on 2026-02-02 against commit bbbbbbbb,\n" in page
    assert "`evidence/installed-lanes-ci-222.json`" in page
    assert lc.current_evidence(root) == "installed-lanes-ci-222.json"


def test_a_second_run_on_the_same_evidence_changes_nothing(tmp_path):
    root = _repo(tmp_path)
    lc.apply(root, lc.plan(root, OLD, NEW, "installed-lanes-ci-222.json"))
    assert lc.plan(root, NEW, NEW, "installed-lanes-ci-222.json") == {}


def test_a_lane_change_is_refused_and_nothing_is_written(tmp_path):
    root = _repo(tmp_path)
    moved = copy.deepcopy(NEW)
    moved["lanes"]["gather"]["verdict"] = "BELOW_BAR"
    with pytest.raises(SystemExit, match="gather"):
        lc.plan(root, OLD, moved, "installed-lanes-ci-222.json")
    assert _read(root, lc.NOTES) == NOTES


@pytest.mark.parametrize("notes, words", [
    (NOTES.replace("commit aaaaaaaa", "commit cccccccc"), "(CI run 111, commit aaaaaaaa)"),
    (NOTES + "Again (CI run 111, commit aaaaaaaa).\n", "found 2"),
    (NOTES.replace("about 0.5 MB", "about 0.7 MB"), "does not follow the old summary"),
    (NOTES.replace("for 1.0.4", "for 1.0.3"), "baseline"),
    (NOTES.replace("1 of 1 lanes", "2 of 1 lanes"), "lane sentence"),
])
def test_a_missing_or_stale_phrase_is_refused(tmp_path, notes, words):
    root = _repo(tmp_path, notes)
    with pytest.raises(SystemExit) as info:
        lc.plan(root, OLD, NEW, "installed-lanes-ci-222.json")
    assert words in str(info.value)


def test_the_new_name_must_name_the_new_run(tmp_path):
    with pytest.raises(SystemExit, match="does not name run 222"):
        lc.plan(_repo(tmp_path), OLD, NEW, "installed-lanes-ci-111.json")


def test_the_repository_copy_names_the_evidence_the_drafts_test_reads():
    """The committed pages carry every phrase for the committed summary, so the
    next --update-copy can find them."""
    import json
    name = lc.current_evidence(REPO)
    evidence = json.loads((REPO / "project-docs" / "lanes" / "evidence" / name)
                          .read_text(encoding="utf-8"))
    assert lc.plan(REPO, evidence, evidence, name) == {}
