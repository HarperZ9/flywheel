"""documentation_maintenance/v2 must reject a submission that only transcribes.

v1 compares the report against the fixture and nothing else, so handing the
fixture back scores as a correct answer. The null floor measured that. v2 keeps
every v1 comparison and adds digests read from the workspace, which the fixture
does not contain.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from harness.cross_harness_oracles_v2 import CHECKER_ID
from test_cross_harness_oracles import _case, _sha, _sync_output

V1 = "documentation_maintenance/v1"


def digests(workspace: Path, row: dict) -> dict:
    """The two facts a candidate can only get by opening the files."""
    return {"content_sha256": _sha((workspace / row["path"]).read_bytes()),
            "code_ref_sha256s": [_sha((workspace / ref).read_bytes()) for ref in row["code_refs"]]}


def case_v2(tmp_path: Path) -> tuple[OracleContext, dict, dict]:
    """The v1 documentation case, rescored under v2 with the digests supplied."""
    context, report, fixture = _case(tmp_path, V1)
    context.oracle_spec["checker_id"] = CHECKER_ID
    workspace = Path(context.scorecard_core["workspace_root"])
    for row in report["surfaces"]:
        row.update(digests(workspace, row))
    _sync_output(context, report)
    return context, report, fixture


def test_a_correct_submission_still_passes(tmp_path: Path) -> None:
    """The control. Without it a rejection could mean the setup is broken."""
    context, _, _ = case_v2(tmp_path)
    result = evaluate_task_oracle(context)
    assert result.state == "pass", result.failure_codes
    assert result.checker_id == CHECKER_ID


def test_echoing_the_fixture_no_longer_scores_as_an_answer(tmp_path: Path) -> None:
    """The defect this checker exists for, stated as a test.

    Under v1 this exact report passes. The fixture carries surface names, paths
    and code refs, so a provider that read only its own input satisfied every
    comparison v1 made.
    """
    context, report, fixture = case_v2(tmp_path)
    echo = {"surfaces": json.loads(json.dumps(fixture["surfaces"])),
            "task_id": report["task_id"], "input_sha256s": report["input_sha256s"],
            "synchronized": False, "gate_passed": False}
    _sync_output(context, echo)
    # Codes are deduplicated, so four missing digests report once.
    assert evaluate_task_oracle(context).failure_codes == ["surface_digest_missing"]

    context.oracle_spec["checker_id"] = V1
    assert evaluate_task_oracle(context).state == "pass"


def test_an_empty_string_is_absent_and_an_empty_list_is_wrong(tmp_path: Path) -> None:
    """The two hollow shapes are not the same claim.

    An empty string says nothing at all. An empty list says this surface has no
    code references, which contradicts a fixture that lists one, so it is a
    wrong answer rather than an absent one.
    """
    context, report, _ = case_v2(tmp_path)
    report["surfaces"][0]["content_sha256"] = ""
    report["surfaces"][1]["code_ref_sha256s"] = []
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == [
        "code_ref_digest_mismatch", "surface_digest_missing"]


@pytest.mark.parametrize("field, value, code", [
    ("content_sha256", "0" * 64, "surface_digest_mismatch"),
    ("code_ref_sha256s", ["0" * 64], "code_ref_digest_mismatch"),
    ("content_sha256", 7, "surface_digest_missing"),
    ("code_ref_sha256s", "not-a-list", "surface_digest_missing"),
])
def test_a_wrong_digest_is_told_apart_from_an_absent_one(tmp_path: Path, field, value, code) -> None:
    context, report, _ = case_v2(tmp_path)
    report["surfaces"][0][field] = value
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == [code]


def test_a_stale_document_is_caught_where_v1_saw_nothing(tmp_path: Path) -> None:
    """The point of the digests, not just their presence.

    Editing a documentation surface after the report was written is exactly the
    drift this task is named for. v1 reads the file and ignores its content.
    """
    context, report, _ = case_v2(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    (workspace / report["surfaces"][0]["path"]).write_text("edited after the fact", encoding="utf-8")
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["surface_digest_mismatch"]

    context.oracle_spec["checker_id"] = V1
    assert evaluate_task_oracle(context).state == "pass"


def test_v2_keeps_every_v1_comparison(tmp_path: Path) -> None:
    """The stricter checker is a superset, so a v1 finding is still a v1 finding."""
    context, report, _ = case_v2(tmp_path)
    report["surfaces"].pop()
    _sync_output(context, report)
    assert "surface_set_mismatch" in evaluate_task_oracle(context).failure_codes

    context, report, _ = case_v2(tmp_path / "second")
    report["surfaces"][0]["code_refs"] = []
    _sync_output(context, report)
    codes = evaluate_task_oracle(context).failure_codes
    assert "code_refs_mismatch" in codes


def test_the_registry_carries_both_versions(tmp_path: Path) -> None:
    """v1 is left in place. A run scored under it stays comparable to itself."""
    from harness.cross_harness_oracles import _CHECKERS

    assert V1 in _CHECKERS and CHECKER_ID in _CHECKERS
    assert _CHECKERS[V1] is not _CHECKERS[CHECKER_ID]
