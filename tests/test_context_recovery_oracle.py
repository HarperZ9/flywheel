import hashlib
import json
from pathlib import Path

import pytest

from harness.cross_harness_null_adapters import echo_report
from harness.cross_harness_context_contract import CONTEXT_RECOVERY_FIXTURE_SCHEMA
from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle

CHECKER = "context_recovery_state/v1"
TASK_ID = "comp-005-context-recovery"
ARTIFACTS = ["context_recovery_state.json", "context_recovery_state.md"]
COMMON_CODES = [
    "artifact_set_mismatch",
    "artifact_not_regular",
    "artifact_not_utf8",
    "artifact_empty",
    "json_invalid",
    "json_duplicate_key",
    "task_id_mismatch",
    "input_hash_mismatch",
    "markdown_task_id_missing",
]
TASK_CODES = [
    "recovery_source_state_mismatch",
    "workspace_state_mismatch",
    "preserved_file_modified",
    "source_drift_not_refused",
    "duplicate_effect_not_idempotent",
    "next_action_mismatch",
    "forbidden_effect_reported",
    "self_report_without_artifact_state",
    "unexpected_workspace_effect",
    "journey_state_mismatch",
    "native_full_session_claim",
    "canonical_markdown_mismatch",
    "workspace_inventory_mismatch",
    "report_schema_mismatch",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, value, *, raw: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw:
        path.write_text(str(value), encoding="utf-8", newline="\n")
    else:
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _sync_output(context: OracleContext, report: dict) -> None:
    json_path = context.artifact_paths[ARTIFACTS[0]]
    md_path = context.artifact_paths[ARTIFACTS[1]]
    _write(json_path, report)
    markdown = md_path.read_text(encoding="utf-8")
    _write(context.raw_output_path, {"artifacts": {ARTIFACTS[0]: report, ARTIFACTS[1]: markdown}})


def _case(tmp_path: Path):
    workspace, attempt = tmp_path / "workspace", tmp_path / "attempt"
    journey_path = "benchmarks/fixtures/cross-harness/context-recovery/journeys.json"
    source = {
        "preview_ref": "cpv_context_recovery_v1",
        "preview_sha256": "a" * 64,
        "source_state_sha256": "b" * 64,
        "event_head_sha256": "c" * 64,
        "selected_files": ["benchmarks/fixtures/cross-harness/context-recovery/slugger.py"],
    }
    workspace_files = [
        {
            "path": "benchmarks/fixtures/cross-harness/context-recovery/slugger.py",
            "role": "target_file",
            "must_preserve": True,
            "body": "def normalize_title(value):\n    return value\n",
        },
        {
            "path": "benchmarks/fixtures/cross-harness/context-recovery/reports/current-status.md",
            "role": "dirty_context",
            "must_preserve": True,
            "body": "unfinished: implement normalize_title exactly\n",
        },
        {
            "path": "benchmarks/fixtures/cross-harness/context-recovery/parallel/owner-note.md",
            "role": "parallel_owned",
            "must_preserve": True,
            "body": "parallel owner branch marker; do not touch\n",
        },
        {
            "path": journey_path,
            "role": "journey_state",
            "must_preserve": True,
            "body": json.dumps({"journeys": [{"id": "first", "continuation": source["preview_ref"]}]}, sort_keys=True) + "\n",
        },
    ]
    for row in workspace_files:
        _write(workspace / row["path"], row["body"], raw=True)
    recovery_contract = {
        "state_basis": "declared_fixture_files",
        "workspace_effect_scope": "sealed_fixture_inventory",
        "native_provenance_scope": "separate_dimension",
        "freeform_prose_scope": "evaluator_rendered_projection_only",
    }
    fixture = {
        "schema": CONTEXT_RECOVERY_FIXTURE_SCHEMA,
        "task_id": TASK_ID,
        "failure_code_vocabulary": {"common": COMMON_CODES, "task": TASK_CODES},
        "accepted_report_fields": [
            "task_id",
            "input_sha256s",
            "recovered_context",
            "workspace_state",
            "preserved_files",
            "source_drift_decisions",
            "duplicate_resolutions",
            "next_action",
            "forbidden_effects",
            "native_provenance_state",
        ],
        "continuation_package": source,
        "workspace_files": [
            {
                "path": row["path"],
                "role": row["role"],
                "must_preserve": row["must_preserve"],
                "expected_sha256": _sha((workspace / row["path"]).read_bytes()),
            }
            for row in workspace_files
        ],
        "drift_cases": [
            {"case_id": "source_drift_before_proposal", "error_code": "SOURCE_DRIFT"},
            {"case_id": "source_drift_after_approval", "error_code": "SOURCE_DRIFT"},
        ],
        "duplicate_cases": [
            {"case_id": "duplicate_start_request", "expected_decision": "idempotent_replay"}
        ],
        "rescue_action": {
            "action_id": "continue-cpv_context_recovery_v1",
            "kind": "repair",
            "selected_files": ["benchmarks/fixtures/cross-harness/context-recovery/slugger.py"],
            "basis_refs": ["cpv_context_recovery_v1", "intake_context_recovery_v1"],
            "description": "Open the private continuation context from the source-bound preview.",
            "required_description_phrases": [
                "private continuation context",
                "source-bound preview",
            ],
        },
        "journey_state": {
            "path": journey_path,
            "expected_preview_ref": source["preview_ref"],
            "expected_count": 1,
        },
        "workspace_inventory": {
            "root": "benchmarks/fixtures/cross-harness/context-recovery",
            "allowed_write_paths": [],
            "entries": [
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/journeys.json", "type": "file", "sha256": _sha((workspace / journey_path).read_bytes())},
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/parallel", "type": "directory"},
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/parallel/owner-note.md", "type": "file", "sha256": _sha((workspace / "benchmarks/fixtures/cross-harness/context-recovery/parallel/owner-note.md").read_bytes())},
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/reports", "type": "directory"},
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/reports/current-status.md", "type": "file", "sha256": _sha((workspace / "benchmarks/fixtures/cross-harness/context-recovery/reports/current-status.md").read_bytes())},
                {"path": "benchmarks/fixtures/cross-harness/context-recovery/slugger.py", "type": "file", "sha256": _sha((workspace / "benchmarks/fixtures/cross-harness/context-recovery/slugger.py").read_bytes())},
            ],
        },
        "forbidden_workspace_paths": ["journeys.json"],
        "forbidden_effects": ["parallel_owned_modified", "source_drift_accepted", "duplicate_journey_created"],
        "forbidden_self_report_phrases": ["completed successfully", "recovered successfully", "all fixed"],
        "forbidden_native_resume_phrases": ["native full-session resume", "hidden provider state"],
        "recovery_contract": recovery_contract,
    }
    fixture_path = workspace / "benchmarks/fixtures/cross-harness/context-recovery-state-v1.json"
    _write(fixture_path, fixture)
    input_hashes = {fixture_path.relative_to(workspace).as_posix(): _sha(fixture_path.read_bytes())}
    for row in fixture["workspace_files"]:
        input_hashes[row["path"]] = _sha((workspace / row["path"]).read_bytes())
    report = {
        "task_id": TASK_ID,
        "input_sha256s": input_hashes,
        "recovered_context": dict(source),
        "workspace_state": [
            {"path": row["path"], "sha256": _sha((workspace / row["path"]).read_bytes()), "role": row["role"]}
            for row in fixture["workspace_files"]
        ],
        "preserved_files": sorted(row["path"] for row in fixture["workspace_files"] if row["must_preserve"]),
        "source_drift_decisions": [
            {"case_id": row["case_id"], "decision": "refuse", "error_code": row["error_code"], "effect_count": 0}
            for row in fixture["drift_cases"]
        ],
        "duplicate_resolutions": [
            {"case_id": "duplicate_start_request", "decision": "idempotent_replay", "new_effect_count": 0, "journey_count": 1}
        ],
        "next_action": {
            "action_id": "continue-cpv_context_recovery_v1",
            "kind": "repair",
            "description": "Open the private continuation context from the source-bound preview.",
            "basis_refs": ["cpv_context_recovery_v1", "intake_context_recovery_v1"],
            "selected_files": ["benchmarks/fixtures/cross-harness/context-recovery/slugger.py"],
        },
        "forbidden_effects": [],
        "native_provenance_state": "separate_dimension",
    }
    json_path, md_path = attempt / ARTIFACTS[0], attempt / ARTIFACTS[1]
    _write(md_path, f"# {TASK_ID}\nSource context selected.\n", raw=True)
    core = {"workspace_root": str(workspace), "attempt_dir": str(attempt)}
    spec = {"checker_id": CHECKER, "fixture": fixture_path.relative_to(workspace).as_posix(), "expected_artifacts": ARTIFACTS}
    context = OracleContext(TASK_ID, spec, attempt / "output.json", {ARTIFACTS[0]: json_path, ARTIFACTS[1]: md_path}, input_hashes, core)
    _sync_output(context, report)
    return context, report, fixture


def test_context_recovery_oracle_passes_from_workspace_and_artifact_state(tmp_path):
    context, _, _ = _case(tmp_path)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("pass", [])
    roles = {row["role"] for row in result.checked_artifacts}
    assert "input_fixture" in roles
    assert any(role.startswith("workspace:parallel_owned:") for role in roles)
    assert result.evidence["preserved_files_checked"] == 4
    assert result.evidence["native_provenance"] == "separate_dimension"


@pytest.mark.parametrize(("mutation", "codes"), [
    ("reported_file_hash", ["workspace_state_mismatch"]),
    ("dirty_file_changed", ["preserved_file_modified", "workspace_state_mismatch"]),
    ("source_drift", ["source_drift_not_refused"]),
    ("duplicate", ["duplicate_effect_not_idempotent"]),
    ("next_action", ["next_action_mismatch"]),
    ("forbidden", ["forbidden_effect_reported"]),
    ("self_report_json", ["self_report_without_artifact_state"]),
    ("self_report_markdown", ["self_report_without_artifact_state"]),
])
def test_context_recovery_oracle_rejects_false_success_controls(tmp_path, mutation, codes):
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    if mutation == "reported_file_hash":
        report["workspace_state"][0]["sha256"] = "0" * 64
    elif mutation == "dirty_file_changed":
        target = workspace / "benchmarks/fixtures/cross-harness/context-recovery/parallel/owner-note.md"
        target.write_text("parallel owner marker changed\n", encoding="utf-8")
    elif mutation == "source_drift":
        report["source_drift_decisions"][0].update(decision="proceed", effect_count=1)
    elif mutation == "duplicate":
        report["duplicate_resolutions"][0].update(decision="new_journey", new_effect_count=1, journey_count=2)
    elif mutation == "next_action":
        report["next_action"].update(selected_files=[], basis_refs=[])
    elif mutation == "forbidden":
        report["forbidden_effects"] = ["parallel_owned_modified"]
    elif mutation == "self_report_json":
        report["claimed_completion"] = "completed successfully"
    elif mutation == "self_report_markdown":
        context.artifact_paths[ARTIFACTS[1]].write_text(f"# {TASK_ID}\nCompleted successfully.\n", encoding="utf-8", newline="\n")
    if mutation != "dirty_file_changed":
        _sync_output(context, report)
    else:
        _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.state == "fail"
    for code in codes:
        assert code in result.failure_codes


@pytest.mark.parametrize("strategy", ["shape", "echo"])
def test_context_recovery_oracle_rejects_shape_only_and_echo_submissions(tmp_path, strategy):
    context, report, fixture = _case(tmp_path)
    candidate = echo_report(report, fixture) if strategy == "echo" else {
        "task_id": TASK_ID,
        "input_sha256s": context.expected_input_sha256s,
        "recovered_context": {},
        "workspace_state": [],
        "preserved_files": [],
        "source_drift_decisions": [],
        "duplicate_resolutions": [],
        "next_action": {},
        "forbidden_effects": [],
        "native_provenance_state": "separate_dimension",
    }
    candidate["task_id"] = TASK_ID
    candidate["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, candidate)
    result = evaluate_task_oracle(context)
    assert result.state == "fail"
    assert result.failure_codes
