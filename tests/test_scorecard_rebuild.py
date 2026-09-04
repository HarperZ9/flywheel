"""Falsifiers for recovering a scorecard from sealed attempt receipts.

This path exists because a run can pay for every attempt and still raise before
it writes the document a reader opens. The temptation at that point is to retype
the numbers, which is the one thing the receipts were sealed to make unnecessary.

So these tests are mostly about the rebuild refusing to launder a receipt that no
longer agrees with the bytes beside it.
"""
import json

import pytest

from harness.cross_harness_artifacts import bind_attempt_receipt
from harness.scorecard_rebuild import DOES_NOT_PROVE, SCHEMA, rebuild


def seal(root, name, **over):
    """Write one attempt directory the way the executor seals it."""
    attempt = root / name
    attempt.mkdir(parents=True)
    output = attempt / "output.txt"
    output.write_text('{"artifacts": {"a.md": "x"}}', encoding="utf-8")
    row = {"provider_role": "flywheel_harness", "task_id": "agt-015", "run_id": "run-1",
           "launched": True, "oracle_state": "pass", "metrics": {"latency_ms": 100.0},
           "raw_output_path": str(output)}
    row.update(over)
    bind_attempt_receipt(row, {"output.txt": output}, attempt / "receipt.json")
    return attempt


def test_a_sealed_run_comes_back_as_a_scorecard_a_reader_can_open(tmp_path):
    seal(tmp_path, "one")
    seal(tmp_path, "two", task_id="agt-016")
    document = rebuild(tmp_path)
    assert document["schema"] == SCHEMA
    assert [row["task_id"] for row in document["rows"]] == ["agt-015", "agt-016"]
    assert document["rebuilt_from"]["receipts_verified"] == 2


def test_an_artifact_edited_after_sealing_is_excluded_and_named(tmp_path):
    """The case this whole path is built to refuse.

    A row whose output no longer hashes to what the receipt recorded is drift.
    Rebuilding it anyway would publish a number backed by bytes nobody has.
    """
    attempt = seal(tmp_path, "tampered")
    seal(tmp_path, "clean", task_id="agt-016")
    (attempt / "output.txt").write_text("something else", encoding="utf-8")
    document = rebuild(tmp_path)
    assert [row["task_id"] for row in document["rows"]] == ["agt-016"]
    assert document["rebuilt_from"]["excluded"] == [
        {"receipt": "tampered/receipt.json", "reason": "receipt_drift"}]
    assert document["rebuilt_from"]["receipts_found"] == 2


def test_a_row_rewritten_inside_its_own_receipt_is_excluded(tmp_path):
    """Editing the verdict is the cheapest way to fake a run."""
    attempt = seal(tmp_path, "lying")
    receipt = json.loads((attempt / "receipt.json").read_text(encoding="utf-8"))
    receipt["receipt_subject"]["final_row"]["oracle_state"] = "pass"
    receipt["receipt_subject"]["final_row"]["task_id"] = "agt-999"
    (attempt / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    seal(tmp_path, "honest", task_id="agt-016")
    document = rebuild(tmp_path)
    assert [row["task_id"] for row in document["rows"]] == ["agt-016"]
    assert document["rebuilt_from"]["excluded"][0]["reason"] == "receipt_drift"


def test_a_file_that_merely_shares_the_name_is_not_read_as_an_attempt(tmp_path):
    (tmp_path / "stray").mkdir()
    (tmp_path / "stray" / "receipt.json").write_text('{"schema": "something/v1"}', encoding="utf-8")
    seal(tmp_path, "real")
    document = rebuild(tmp_path)
    assert len(document["rows"]) == 1
    assert document["rebuilt_from"]["excluded"] == [
        {"receipt": "stray/receipt.json", "reason": "not_an_attempt_receipt"}]


def test_unreadable_bytes_are_excluded_rather_than_crashing_the_rebuild(tmp_path):
    (tmp_path / "half").mkdir()
    (tmp_path / "half" / "receipt.json").write_text("{ truncated", encoding="utf-8")
    seal(tmp_path, "real")
    assert rebuild(tmp_path)["rebuilt_from"]["excluded"][0]["reason"] == "not_an_attempt_receipt"


def test_a_run_with_nothing_verifiable_refuses_instead_of_emitting_an_empty_run(tmp_path):
    """An empty comparison reads as a run where every harness scored zero."""
    with pytest.raises(ValueError, match="no verifiable attempt receipt"):
        rebuild(tmp_path)


def test_the_same_run_rebuilds_to_the_same_bytes(tmp_path):
    """A rebuild that varies cannot be re-run as a check on an earlier one."""
    seal(tmp_path, "b", task_id="agt-016")
    seal(tmp_path, "a")
    first, second = rebuild(tmp_path), rebuild(tmp_path)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert [row["task_id"] for row in first["rows"]] == ["agt-015", "agt-016"]


def test_the_document_says_a_missing_attempt_leaves_no_receipt_to_find(tmp_path):
    seal(tmp_path, "one")
    assert rebuild(tmp_path)["does_not_prove"] == DOES_NOT_PROVE
    assert any("absent here rather than failed" in item for item in DOES_NOT_PROVE)


def test_a_rebuild_says_the_run_never_reached_its_own_source_check(tmp_path):
    """Rebuilding is not evidence the run ended well. It is evidence it did not."""
    seal(tmp_path, "one")
    assert rebuild(tmp_path)["source_tree_state"] == "unsealed"


def test_a_rebuild_over_a_sealed_run_carries_what_that_run_concluded(tmp_path):
    seal(tmp_path, "one")
    (tmp_path / "run.json").write_text('{"source_tree_state": "drift"}', encoding="utf-8")
    assert rebuild(tmp_path)["source_tree_state"] == "drift"


def test_a_run_receipt_missing_the_field_is_unrecorded_and_not_assumed_clean(tmp_path):
    seal(tmp_path, "one")
    (tmp_path / "run.json").write_text('{"run_id": "run-1"}', encoding="utf-8")
    assert rebuild(tmp_path)["source_tree_state"] == "unrecorded"
