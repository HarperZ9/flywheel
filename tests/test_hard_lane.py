"""test_hard_lane.py — the contamination freshness gate is re-checkable.

Success criteria:
  - a task public AFTER a model's cutoff is FRESH; on/before it is CONTAMINATED;
    a missing/malformed date is UNKNOWN.
  - load_lane round-trips a JSONL manifest; admit partitions by freshness and
    flags unlicensed tasks.
"""
from harness.hard_lane import (
    VERDICT_CONTAMINATED,
    VERDICT_FRESH,
    VERDICT_UNKNOWN,
    LaneTask,
    admit,
    freshness,
    freshness_report,
    load_lane,
    write_lane,
)


def test_freshness_verdicts():
    assert freshness("2026-06-01", "2025-12-01") == VERDICT_FRESH
    assert freshness("2025-01-01", "2025-12-01") == VERDICT_CONTAMINATED
    assert freshness("2025-12-01", "2025-12-01") == VERDICT_CONTAMINATED   # same day = conservative
    assert freshness("", "2025-12-01") == VERDICT_UNKNOWN
    assert freshness("2026-06-01", "not-a-date") == VERDICT_UNKNOWN


def test_freshness_report_shape():
    t = LaneTask(task_id="t1", source="livecodebench", license="CC-BY-4.0",
                 public_date="2026-06-01", oracle_cmd="pytest")
    r = freshness_report(t, "2025-12-01")
    assert r["verdict"] == VERDICT_FRESH and r["task_id"] == "t1" and len(r["fingerprint"]) == 16


def test_load_and_admit(tmp_path):
    tasks = [
        LaneTask(task_id="fresh", source="s", license="MIT", public_date="2026-06-01", oracle_cmd="p"),
        LaneTask(task_id="old", source="s", license="MIT", public_date="2024-01-01", oracle_cmd="p"),
        LaneTask(task_id="nolic", source="s", license="", public_date="2026-06-01", oracle_cmd="p"),
    ]
    loaded = load_lane(write_lane(tasks, tmp_path / "lane.jsonl"))
    assert [t.task_id for t in loaded] == ["fresh", "old", "nolic"]

    rep = admit(loaded, "2025-12-01")
    assert set(rep["fresh"]) == {"fresh", "nolic"}       # both public after the cutoff
    assert rep["contaminated"] == ["old"]
    assert rep["unlicensed"] == ["nolic"]                # flagged even though it is fresh
    assert rep["counts"][VERDICT_FRESH] == 2
