import copy
import hashlib
import json
from pathlib import Path

import pytest

from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from kv_source_case_data import CASES, _answered, _record


CHECKER_ID = "kv_source_derived_strict_json/v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, value, *, raw: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw:
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

def _fixture(task_id: str, records: list[dict]) -> dict:
    return {
        "schema": "flywheel.kv-source-only-fixture/v1",
        "task_id": task_id,
        "family": "synthetic source-only KV test",
        "question": f"Derive {task_id} from source records.",
        "citation_order": "unordered_set",
        "source_input_ref": f"model_inputs/{task_id}.source.jsonl",
        "source_input_sha256": "0" * 64,
        "source_records": records,
    }


def _sync_output(context: OracleContext, report: dict) -> None:
    _write(context.artifact_paths["report.json"], report)
    markdown = context.artifact_paths["report.md"].read_bytes().decode("utf-8")
    _write(context.raw_output_path, {"artifacts": {"report.json": report, "report.md": markdown}})


def _kv_case(tmp_path: Path, task_id: str, *, result: dict | None = None) -> tuple[OracleContext, dict, dict]:
    records, expected = CASES[task_id]
    workspace, attempt = tmp_path / "workspace", tmp_path / "attempt"
    fixture_ref = f"model_inputs/{task_id}.source.fixture.json"
    prompt_ref = f"prompts_sanitized/{task_id}.prompt.txt"
    fixture = _fixture(task_id, copy.deepcopy(records))
    fixture_path, prompt_path = workspace / fixture_ref, workspace / prompt_ref
    _write(fixture_path, fixture)
    _write(prompt_path, task_id, raw=True)
    input_hashes = {fixture_ref: _sha(fixture_path.read_bytes()), prompt_ref: _sha(prompt_path.read_bytes())}
    raw, receipt = attempt / "raw.txt", attempt / "receipt.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("raw output", encoding="utf-8")
    receipt.write_text("{}", encoding="utf-8")
    core = {
        "raw_prompt_sha256": "a" * 64,
        "tool_policy_sha256": "b" * 64,
        "attempt_dir": str(attempt),
        "workspace_root": str(workspace),
        "raw_artifact_sha256": _sha(raw.read_bytes()),
        "receipt_sha256": _sha(receipt.read_bytes()),
        "orthogonal_states": {"execution_state": "completed", "oracle_state": "not_run", "receipt_state": "verified"},
    }
    spec = {"checker_id": CHECKER_ID, "fixture": fixture_ref, "expected_artifacts": ["report.json", "report.md"], "citation_order": "unordered_set"}
    json_path, md_path = attempt / "report.json", attempt / "report.md"
    report = {"task_id": task_id, "input_sha256s": input_hashes, "result": copy.deepcopy(result if result is not None else expected)}
    _write(json_path, report)
    _write(md_path, f"# {task_id}\n", raw=True)
    context = OracleContext(task_id, spec, attempt / "output.json", {"report.json": json_path, "report.md": md_path}, input_hashes, core)
    _sync_output(context, report)
    return context, report, fixture


@pytest.mark.parametrize("task_id", sorted(CASES))
def test_kv_source_oracle_derives_all_twelve_task_results_from_source_records(tmp_path, task_id):
    context, _, _ = _kv_case(tmp_path, task_id)

    result = evaluate_task_oracle(context)

    assert result.state == "pass"
    assert result.failure_codes == []
    assert result.evidence["source_record_count"] == len(CASES[task_id][0])
    assert result.evidence["citation_count"] == len(CASES[task_id][1]["citations"])


def test_kv_source_oracle_accepts_unordered_citation_set(tmp_path):
    expected = copy.deepcopy(CASES["kv-msr-002-route-reconstruction"][1])
    expected["citations"] = list(reversed(expected["citations"]))
    context, _, _ = _kv_case(tmp_path, "kv-msr-002-route-reconstruction", result=expected)

    assert evaluate_task_oracle(context).state == "pass"


def test_kv_source_oracle_rejects_wrong_answer_and_copytrap_citation(tmp_path):
    wrong = copy.deepcopy(CASES["kv-msr-001-incident-reconstruction"][1])
    wrong["answer"]["current_state"] = "copied-private-answer"
    wrong["citations"] = ["private-oracle:copy-trap"]
    context, _, _ = _kv_case(tmp_path, "kv-msr-001-incident-reconstruction", result=wrong)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert {"answer_mismatch", "citation_unknown", "citations_mismatch"} <= set(result.failure_codes)


@pytest.mark.parametrize(
    ("task_id", "field", "replacement"),
    [
        ("kv-rap-001-policy-precedence", "cache_reuse_between_arms", 1),
        ("kv-msr-001-incident-reconstruction", "latest_sequence", 2.0),
    ],
)
def test_kv_source_oracle_rejects_json_type_equivalent_answer_values(tmp_path, task_id, field, replacement):
    wrong = copy.deepcopy(CASES[task_id][1])
    wrong["answer"][field] = replacement
    context, _, _ = _kv_case(tmp_path, task_id, result=wrong)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["answer_mismatch"]


def test_kv_source_oracle_rejects_json_type_equivalent_abstention_values(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-abst-001-f16-settings-missing")
    for row in fixture["source_records"]:
        if row["record_id"] == "rule:treatment-compliance":
            row["fields"]["required_evidence"] = True
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    wrong = copy.deepcopy(report["result"])
    wrong["missing_evidence"] = [1]
    report["result"] = wrong
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["missing_evidence_mismatch"]


def test_kv_source_oracle_derives_release_approval_boolean_from_current_source_record(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-rap-002-release-approval")
    for row in fixture["source_records"]:
        if row["record_id"] == "approval:default-change:absent":
            row["fields"]["default_change_approved"] = True
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    report["result"]["answer"]["blockers"] = ["heavy_source_tests_pending"]
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["answer_mismatch"]


def test_kv_source_oracle_rejects_duplicate_citations(tmp_path):
    duplicated = copy.deepcopy(CASES["kv-cdr-001-retention-authority"][1])
    duplicated["citations"] = duplicated["citations"] + [duplicated["citations"][0]]
    context, _, _ = _kv_case(tmp_path, "kv-cdr-001-retention-authority", result=duplicated)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert "citation_duplicate" in result.failure_codes


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("duplicate_key", "json_duplicate_key"),
        ("trailing_text", "json_invalid"),
        ("malformed_json", "json_invalid"),
    ],
)
def test_kv_source_oracle_strict_json_controls_remain_malformed(tmp_path, mutation, code):
    context, report, _ = _kv_case(tmp_path, "kv-msr-001-incident-reconstruction")
    if mutation == "duplicate_key":
        context.artifact_paths["report.json"].write_text(
            '{"task_id":"kv-msr-001-incident-reconstruction","input_sha256s":{},"result":{"task_id":"x","task_id":"y"}}',
            encoding="utf-8",
        )
    elif mutation == "trailing_text":
        context.artifact_paths["report.json"].write_text(json.dumps(report) + "\nextra", encoding="utf-8")
    else:
        context.artifact_paths["report.json"].write_text('{"task_id":', encoding="utf-8")

    result = evaluate_task_oracle(context)

    assert result.state == "malformed"
    assert result.failure_codes == [code]


def test_kv_source_oracle_requires_missing_evidence_field_for_abstention(tmp_path):
    abstention = copy.deepcopy(CASES["kv-abst-001-f16-settings-missing"][1])
    abstention.pop("missing_evidence")
    context, _, _ = _kv_case(tmp_path, "kv-abst-001-f16-settings-missing", result=abstention)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["missing_evidence_missing"]


def test_kv_source_oracle_binds_fixture_hash_before_derivation(tmp_path):
    context, _, _ = _kv_case(tmp_path, "kv-rap-001-policy-precedence")
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    fixture_path.write_text("{}", encoding="utf-8")

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["input_hash_mismatch"]


def test_kv_source_oracle_rejects_reference_like_source_fixture(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-msr-001-incident-reconstruction")
    fixture["source_records"][0]["fields"]["answer"] = {"current_state": "repair"}
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "malformed"
    assert result.failure_codes == ["json_invalid"]


def test_kv_source_oracle_derives_supporting_doc_from_current_rsm_source_record(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-rsm-001-lane-symbol-match")
    for row in fixture["source_records"]:
        if row["record_id"] == "repo-file:WORKSPACE-INDEX.md":
            row["fields"]["path"] = "ECOSYSTEM.md"
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["answer_mismatch"]


def test_kv_source_oracle_requires_rsm_supporting_doc_record(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-rsm-001-lane-symbol-match")
    fixture["source_records"] = [
        row for row in fixture["source_records"]
        if row["record_id"] != "repo-file:WORKSPACE-INDEX.md"
    ]
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "malformed"
    assert result.failure_codes == ["json_invalid"]


def test_kv_source_oracle_unknown_task_never_passes(tmp_path):
    workspace, attempt = tmp_path / "workspace", tmp_path / "attempt"
    fixture_ref = "model_inputs/kv-unknown.source.fixture.json"
    prompt_ref = "prompts_sanitized/kv-unknown.prompt.txt"
    fixture = _fixture("kv-unknown", [_record("record:one", "note", value="seen")])
    _write(workspace / fixture_ref, fixture)
    _write(workspace / prompt_ref, "kv-unknown", raw=True)
    input_hashes = {fixture_ref: _sha((workspace / fixture_ref).read_bytes()), prompt_ref: _sha((workspace / prompt_ref).read_bytes())}
    report = {"task_id": "kv-unknown", "input_sha256s": input_hashes, "result": _answered("kv-unknown", {"value": "seen"}, ["record:one"])}
    _write(attempt / "report.json", report)
    _write(attempt / "report.md", "# kv-unknown\n", raw=True)
    markdown = (attempt / "report.md").read_bytes().decode("utf-8")
    _write(attempt / "output.json", {"artifacts": {"report.json": report, "report.md": markdown}})
    core = {"raw_prompt_sha256": "a" * 64, "tool_policy_sha256": "b" * 64, "attempt_dir": str(attempt), "workspace_root": str(workspace), "raw_artifact_sha256": "c" * 64, "receipt_sha256": "d" * 64, "orthogonal_states": {"execution_state": "completed", "oracle_state": "not_run", "receipt_state": "verified"}}
    context = OracleContext("kv-unknown", {"checker_id": CHECKER_ID, "fixture": fixture_ref, "expected_artifacts": ["report.json", "report.md"]}, attempt / "output.json", {"report.json": attempt / "report.json", "report.md": attempt / "report.md"}, input_hashes, core)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert result.failure_codes == ["unknown_kv_task"]
