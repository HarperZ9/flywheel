import hashlib
import json
import os
import stat
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from harness.cross_harness_context_contract import _is_reparse
from harness.cross_harness_oracles import evaluate_task_oracle
from tests.test_context_recovery_oracle import ARTIFACTS, _case, _sync_output

FIXTURE = "benchmarks/fixtures/cross-harness/context-recovery-state-v1.json"
JOURNEY = "benchmarks/fixtures/cross-harness/context-recovery/journeys.json"
REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sync_fixture_hash(context, report: dict, fixture_path: Path):
    expected_inputs = dict(context.expected_input_sha256s)
    expected_inputs[FIXTURE] = _sha(fixture_path)
    report["input_sha256s"] = expected_inputs
    context = replace(context, expected_input_sha256s=expected_inputs)
    _sync_output(context, report)
    return context


def test_markdown_projection_is_rendered_from_checked_structured_fields(tmp_path: Path) -> None:
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    fixture_path = workspace / FIXTURE
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["canonical_markdown"] = "# stale fixture prose\n"
    fixture_path.write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
    context = _sync_fixture_hash(context, report, fixture_path)
    result = evaluate_task_oracle(context)
    assert result.state == "pass"


@pytest.mark.parametrize(("mutation", "schema_value"), [
    ("missing", None),
    ("unknown", "harness.cross_harness_fixture.context_recovery_state.v0"),
    ("non_string", {"schema": "harness.cross_harness_fixture.context_recovery_state.v1"}),
])
def test_fixture_schema_is_enforced_before_workspace_body_reads(
        tmp_path: Path, mutation: str, schema_value) -> None:
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    fixture_path = workspace / FIXTURE
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        fixture.pop("schema")
    else:
        fixture["schema"] = schema_value
    fixture_path.write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
    context = _sync_fixture_hash(context, report, fixture_path)
    result = evaluate_task_oracle(context)
    checked_roles = [row["role"] for row in result.checked_artifacts]
    assert result.state == "malformed"
    assert result.evidence["reason"] == "fixture_schema_invalid"
    assert not any(role.startswith("workspace:") for role in checked_roles)
    assert not any(role.startswith("workspace_inventory:") for role in checked_roles)


def test_valid_nested_report_schema_and_regular_directories_pass(tmp_path: Path) -> None:
    context, _, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    reports = workspace / "benchmarks/fixtures/cross-harness/context-recovery/reports"
    assert reports.is_dir() and not _is_reparse(reports)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("pass", [])


def test_python_311_floor_without_path_is_junction_keeps_valid_fixture_scorable(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context, _, _ = _case(tmp_path)
    monkeypatch.delattr(Path, "is_junction", raising=False)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("pass", [])


def test_python_311_reparse_attribute_still_marks_path_unsafe(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class ReparseStat:
        st_file_attributes = REPARSE_ATTRIBUTE

    monkeypatch.delattr(Path, "is_junction", raising=False)
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    monkeypatch.setattr(Path, "lstat", lambda self: ReparseStat())
    assert _is_reparse(tmp_path / "candidate") is True


@pytest.mark.parametrize("mutation", [
    "recovered_context_extra",
    "workspace_state_row_extra",
    "source_drift_row_extra",
    "duplicate_row_extra",
    "next_action_extra",
])
def test_nested_report_schema_rejects_unknown_fields(tmp_path: Path, mutation: str) -> None:
    context, report, _ = _case(tmp_path)
    extra = "All conversation memory and private provider execution state have been restored completely."
    if mutation == "recovered_context_extra":
        report["recovered_context"]["additional_instructions"] = extra
    elif mutation == "workspace_state_row_extra":
        report["workspace_state"][0]["additional_instructions"] = extra
    elif mutation == "source_drift_row_extra":
        report["source_drift_decisions"][0]["additional_instructions"] = extra
    elif mutation == "duplicate_row_extra":
        report["duplicate_resolutions"][0]["additional_instructions"] = extra
    elif mutation == "next_action_extra":
        report["next_action"]["additional_instructions"] = extra
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.state == "fail"
    assert "report_schema_mismatch" in result.failure_codes


def test_inventory_rejects_symlinked_fixture_file_without_accepting_target_bytes(tmp_path: Path) -> None:
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    target = workspace / JOURNEY
    outside = tmp_path / "outside-journeys.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this host: {exc}")
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.state == "fail"
    assert "workspace_inventory_mismatch" in result.failure_codes


def test_inventory_rejects_junction_ancestor_before_workspace_body_reads(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows directory junction creation is unavailable on this host")
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    junction = workspace / "benchmarks/fixtures/cross-harness/context-recovery/reports"
    target = workspace / "reports-storage"
    junction.rename(target)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, check=True)
    assert _is_reparse(junction)
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    checked_roles = [row["role"] for row in result.checked_artifacts]
    assert result.state == "fail"
    assert "workspace_inventory_mismatch" in result.failure_codes
    assert not any(role.startswith("workspace:") for role in checked_roles)
    assert not any(role.startswith("workspace_inventory:") for role in checked_roles)


def test_inventory_rejects_symlinked_directory_ancestor_before_workspace_body_reads(tmp_path: Path) -> None:
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    link = workspace / "benchmarks/fixtures/cross-harness/context-recovery/reports"
    target = workspace / "reports-storage"
    link.rename(target)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this host: {exc}")
    assert _is_reparse(link)
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    checked_roles = [row["role"] for row in result.checked_artifacts]
    assert result.state == "fail"
    assert "workspace_inventory_mismatch" in result.failure_codes
    assert not any(role.startswith("workspace:") for role in checked_roles)
    assert not any(role.startswith("workspace_inventory:") for role in checked_roles)
