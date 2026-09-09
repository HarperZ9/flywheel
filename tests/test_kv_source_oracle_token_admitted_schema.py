import copy
import hashlib
import json
from pathlib import Path
import pytest

from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from kv_source_case_data import CASES


CHECKER_ID = "kv_source_derived_strict_json/v1"
TOKEN_ADMITTED_SCHEMA = "flywheel.kv-source-only-fixture/v2-token-admitted"


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
        "schema": TOKEN_ADMITTED_SCHEMA,
        "task_id": task_id,
        "family": "synthetic token-admitted source-only KV test",
        "question": f"Derive {task_id} from source records.",
        "citation_order": "unordered_set",
        "source_input_ref": f"model_inputs/{task_id}.source.jsonl",
        "source_input_sha256": "0" * 64,
        "source_records": records,
    }


def _sync_output(context: OracleContext, report: dict) -> None:
    markdown = context.artifact_paths["report.md"].read_bytes().decode("utf-8")
    _write(context.artifact_paths["report.json"], report)
    _write(context.raw_output_path, {"artifacts": {"report.json": report, "report.md": markdown}})


def _kv_case(tmp_path: Path, task_id: str, *, result: dict | None = None) -> tuple[OracleContext, dict, dict]:
    records, expected = CASES[task_id]
    workspace, attempt = tmp_path / "workspace", tmp_path / "attempt"
    fixture_ref = f"model_inputs/{task_id}.source.fixture.json"
    prompt_ref = f"prompts_sanitized/{task_id}.prompt.txt"
    fixture = _fixture(task_id, copy.deepcopy(records))
    _write(workspace / fixture_ref, fixture)
    _write(workspace / prompt_ref, task_id, raw=True)
    input_hashes = {
        fixture_ref: _sha((workspace / fixture_ref).read_bytes()),
        prompt_ref: _sha((workspace / prompt_ref).read_bytes()),
    }
    report = {
        "task_id": task_id,
        "input_sha256s": input_hashes,
        "result": copy.deepcopy(result if result is not None else expected),
    }
    json_path, md_path = attempt / "report.json", attempt / "report.md"
    _write(json_path, report)
    _write(md_path, f"# {task_id}\n", raw=True)
    core = {"workspace_root": str(workspace), "attempt_dir": str(attempt)}
    spec = {
        "checker_id": CHECKER_ID,
        "fixture": fixture_ref,
        "expected_artifacts": ["report.json", "report.md"],
        "citation_order": "unordered_set",
    }
    context = OracleContext(
        task_id,
        spec,
        attempt / "output.json",
        {"report.json": json_path, "report.md": md_path},
        input_hashes,
        core,
    )
    _sync_output(context, report)
    return context, report, fixture


def test_kv_source_oracle_accepts_explicit_token_admitted_v2_fixture_shape(tmp_path):
    context, _, _ = _kv_case(tmp_path, "kv-msr-001-incident-reconstruction")

    result = evaluate_task_oracle(context)

    assert result.state == "pass"
    assert result.failure_codes == []


def test_kv_source_oracle_rejects_token_admitted_v2_fixture_missing_prompt_question(tmp_path):
    context, report, fixture = _kv_case(tmp_path, "kv-msr-001-incident-reconstruction")
    fixture.pop("question")
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)

    result = evaluate_task_oracle(context)

    assert result.state == "malformed"
    assert result.failure_codes == ["json_invalid"]
    assert result.evidence["reason"] == "fixture_token_admitted_shape_invalid"


@pytest.mark.parametrize("task_id", ["kv-sta-001-endpoint-gate-argv", "kv-sta-002-manifest-argv"])
def test_kv_source_oracle_requires_explicit_structured_task_cwd_source_field(tmp_path, task_id):
    expected = copy.deepcopy(CASES[task_id][1])
    expected["answer"]["cwd"] = "scratch/kv"
    context, _, fixture = _kv_case(tmp_path, task_id, result=expected)
    for row in fixture["source_records"]:
        if row["record_id"] == "path-contract:temp-only":
            row["fields"].pop("cwd")
    fixture_path = Path(context.scorecard_core["workspace_root"]) / context.oracle_spec["fixture"]
    _write(fixture_path, fixture)
    context.expected_input_sha256s[context.oracle_spec["fixture"]] = _sha(fixture_path.read_bytes())
    _sync_output(context, {"task_id": context.task_id, "input_sha256s": context.expected_input_sha256s, "result": expected})

    result = evaluate_task_oracle(context)

    assert result.state == "malformed"
    assert result.failure_codes == ["json_invalid"]
    assert result.evidence["reason"] == "fixture_cwd_missing"


def test_kv_source_oracle_flags_unrequested_structured_command_flags(tmp_path):
    wrong = copy.deepcopy(CASES["kv-sta-002-manifest-argv"][1])
    wrong["answer"]["argv"].extend(["--provider", "local_kv_f16"])
    context, _, _ = _kv_case(tmp_path, "kv-sta-002-manifest-argv", result=wrong)

    result = evaluate_task_oracle(context)

    assert result.state == "fail"
    assert "forbidden_claim_or_flag" in result.failure_codes
