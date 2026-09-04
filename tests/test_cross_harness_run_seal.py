"""Falsifiers for what a run leaves behind when it ends badly.

A run that raises on its way out has already spent the money. The question these
tests settle is whether the attempts it paid for are still readable afterwards,
and whether a reader can tell that the run ended under a drifted source tree.
"""
import json

import pytest

import hashlib

from harness.cross_harness_run_seal import (RUN_SCHEMA, SCORECARD_SCHEMA, TREE_STATE_LIMITS,
                                            scorecard_limitations, scorecard_provenance, seal_run)

SNAPSHOT = {"schema": "harness.cross-harness-source-snapshot/v1", "sha256": "a" * 64}
MOVED = {"schema": "harness.cross-harness-source-snapshot/v1", "sha256": "b" * 64}
ROWS = [{"provider_role": "flywheel_harness", "task_id": "agt-015", "oracle_state": "pass"}]


def seal(tmp_path, after=SNAPSHOT):
    return seal_run(tmp_path, run_id="run-1", phase="focused_run", rows=ROWS,
                    before=SNAPSHOT, after=after, indexed=[])


def test_a_clean_run_writes_both_documents(tmp_path):
    run, state = seal(tmp_path)
    assert state == "clean" and run["schema"] == RUN_SCHEMA
    scorecard = json.loads((tmp_path / "comparison-input.json").read_text(encoding="utf-8"))
    assert scorecard["schema"] == SCORECARD_SCHEMA and scorecard["rows"] == ROWS
    assert json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))["rows"] == ROWS


def test_a_drifted_tree_still_leaves_the_attempts_it_paid_for(tmp_path):
    """The regression this module exists for.

    The 2026-09-04 run raised on drift before writing anything, so 35 sealed
    attempts had no document to read them from and the only way to publish was
    to retype the numbers.
    """
    run, state = seal(tmp_path, after=MOVED)
    assert state == "drift"
    assert json.loads((tmp_path / "comparison-input.json").read_text(encoding="utf-8"))["rows"] == ROWS
    assert run["source_tree_state"] == "drift"


def test_a_reader_of_the_scorecard_alone_can_still_see_the_drift(tmp_path):
    """The scorecard travels without the run receipt. It has to carry this itself."""
    seal(tmp_path, after=MOVED)
    scorecard = json.loads((tmp_path / "comparison-input.json").read_text(encoding="utf-8"))
    assert scorecard["source_tree_state"] == "drift"


def test_the_run_receipt_keeps_both_snapshots_so_the_drift_can_be_checked(tmp_path):
    run, _ = seal(tmp_path, after=MOVED)
    assert run["source_snapshot_before"] == SNAPSHOT and run["source_snapshot_after"] == MOVED


def test_both_documents_reach_the_artifact_index(tmp_path):
    """An unindexed document is one no verifier will ever open."""
    seal(tmp_path)
    index = json.loads((tmp_path / "artifact-index.json").read_text(encoding="utf-8"))
    named = json.dumps(index)
    assert "comparison-input.json" in named and "run.json" in named


def test_the_documents_are_byte_stable_across_two_seals(tmp_path):
    """A run receipt that varies cannot be re-derived as a check on itself."""
    seal(tmp_path)
    first = (tmp_path / "run.json").read_bytes()
    seal(tmp_path)
    assert (tmp_path / "run.json").read_bytes() == first


def test_a_value_json_cannot_represent_is_refused_rather_than_written(tmp_path):
    """NaN would round-trip as a bare token no strict reader accepts."""
    with pytest.raises(ValueError):
        seal_run(tmp_path, run_id="run-1", phase="focused_run",
                 rows=[{"latency_ms": float("nan")}], before=SNAPSHOT, after=SNAPSHOT, indexed=[])


def limits(tmp_path, name, **doc):
    path = tmp_path / name
    path.write_text(json.dumps({"schema": SCORECARD_SCHEMA, "rows": ROWS, **doc}), encoding="utf-8")
    return scorecard_limitations([path])


def test_a_run_that_never_sealed_says_its_commit_line_was_never_checked(tmp_path):
    """The state the 2026-09-04 rebuild is in. The rows name a commit anyway."""
    stated = limits(tmp_path, "rebuilt.json", source_tree_state="unsealed")
    assert stated == [TREE_STATE_LIMITS["unsealed"]]
    assert "narrower claim" in stated[0]


def test_a_drifted_run_says_the_commit_does_not_describe_the_tree(tmp_path):
    assert limits(tmp_path, "drifted.json", source_tree_state="drift") == [TREE_STATE_LIMITS["drift"]]


def test_a_clean_run_adds_no_limitation(tmp_path):
    assert limits(tmp_path, "clean.json", source_tree_state="clean") == []


def test_a_scorecard_written_before_the_field_existed_is_left_alone(tmp_path):
    """Inventing a limitation for it would be as wrong as dropping a real one."""
    assert limits(tmp_path, "old.json") == []


def test_an_unreadable_scorecard_contributes_nothing_rather_than_crashing(tmp_path):
    (tmp_path / "half.json").write_text("{ truncated", encoding="utf-8")
    assert scorecard_limitations([tmp_path / "half.json", tmp_path / "gone.json"]) == []


def test_pooling_two_runs_in_the_same_state_states_it_once(tmp_path):
    """A limitation repeated per input reads as several separate problems."""
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(
            json.dumps({"rows": ROWS, "source_tree_state": "unsealed"}), encoding="utf-8")
    assert len(scorecard_limitations([tmp_path / "a.json", tmp_path / "b.json"])) == 1


def test_a_scorecard_inside_the_repo_keeps_the_path_that_means_the_same_to_a_reader(tmp_path):
    inside = tmp_path / "docs" / "run.json"
    inside.parent.mkdir()
    inside.write_bytes(b"{}")
    entry = scorecard_provenance([inside], tmp_path)[0]
    assert entry["repo_path"] == "docs/run.json"
    assert entry["sha256"] == hashlib.sha256(b"{}").hexdigest()


def test_a_scorecard_outside_the_repo_is_hashed_and_never_pathed(tmp_path):
    """The real case: the run was rebuilt into a scratchpad outside the tree."""
    elsewhere = tmp_path / "scratch" / "run.json"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(b"{}")
    entry = scorecard_provenance([elsewhere], tmp_path / "repo")[0]
    assert entry["repo_path"] is None
    assert entry["name"] == "run.json" and entry["sha256"]


def test_a_scorecard_that_cannot_be_read_is_named_rather_than_dropped(tmp_path):
    """Silently shortening the list would understate what the report pooled."""
    entry = scorecard_provenance([tmp_path / "gone.json"], tmp_path)[0]
    assert entry["name"] == "gone.json" and entry["sha256"] is None
