import hashlib
import json
import sys
from pathlib import Path

import pytest

from harness.cross_harness_artifacts import recheck_attempt_receipt
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult
from tests.test_cross_harness_executor import FakeAdapter, _one_task, _runtime


def _run_returned_output(tmp_path, output, *, expected=("result.json",), usage=None, tool_trace=None):
    source = tmp_path / "source"; source.mkdir()
    result = AdapterResult("returned", output, tool_trace or [], 1, "14B", "seeded", "", "", {}, usage or {}, [], [], "structured_provider_response")
    return execute_cross_harness_manifest(_one_task(source, expected=expected), _runtime(["local_14b"]),
        {"local_14b": FakeAdapter(result=result)}, artifact_root=tmp_path / "artifacts", source_root=source,
        run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)["rows"][0]


def _receipt_final_row(row):
    return json.loads(Path(row["receipt_path"]).read_text(encoding="utf-8"))["receipt_subject"]["final_row"]


def test_malformed_output_diagnostics_are_typed_and_receipt_bound(tmp_path):
    output = '```json\n{"artifacts":{"result.json":{}}\n```'
    final_usage = {"eval_count": SHARED_TOOL_POLICY["max_output_tokens"]}
    usage = {"inner_calls": 1, "per_call": [final_usage], "aggregate": final_usage}
    tool_trace = [{"source": "codex_inner", "inner_call": 1, "type": "turn.completed", "usage": final_usage}]
    row = _run_returned_output(tmp_path, output, usage=usage, tool_trace=tool_trace)
    diagnostics = row["output_diagnostics"]
    assert (row["execution_state"], row["oracle_state"], row["primary_outcome"], row["receipt_state"]) == ("malformed", "not_run", "malformed", "verified")
    assert diagnostics["schema"] == "harness.cross-harness-output-diagnostics/v1"
    assert diagnostics["parser"]["status"] == "json_decode_error"
    assert set(diagnostics["codes"]) >= {"json_parse_error", "markdown_fence_at_start", "length_cap_reached"}
    assert diagnostics["runtime"]["length_cap_reached"]["does_not_prove"] == ["truncation"]
    assert diagnostics["artifact_comparison"]["status"] == "not_checked"
    assert _receipt_final_row(row)["output_diagnostics"] == diagnostics
    assert recheck_attempt_receipt(Path(row["receipt_path"]), {**row, "execution_state": "returned", "oracle_state": "pass", "primary_outcome": "completed", "status": "executed"}) == "drift"
    assert recheck_attempt_receipt(Path(row["receipt_path"]), {**row, "output_diagnostics": {**diagnostics, "codes": []}}) == "drift"
    assert Path(row["raw_output_path"]).read_bytes() == output.encode()
    assert row["raw_output_sha256"] == hashlib.sha256(output.encode()).hexdigest()


@pytest.mark.parametrize(("output", "expected_codes", "missing"), [
    ('{"artifacts":{"result.json":{},"result.json":{}}}', {"duplicate_key_rejected"}, []),
    ('{"artifacts":{"result.json":{}}}', {"artifact_set_mismatch", "missing_declared_artifact"}, ["result.md"]),
])
def test_malformed_output_diagnostics_use_parser_facts_not_repair(tmp_path, output, expected_codes, missing):
    row = _run_returned_output(tmp_path, output, expected=("result.json", "result.md"))
    diagnostics = row["output_diagnostics"]
    assert set(diagnostics["codes"]) >= expected_codes
    assert diagnostics["artifact_comparison"].get("missing_declared_artifacts", []) == missing
    assert (row["execution_state"], row["oracle_state"], row["primary_outcome"]) == ("malformed", "not_run", "malformed")


def test_integer_parser_limit_is_not_labeled_duplicate_key(tmp_path):
    digit_limit = sys.get_int_max_str_digits()
    if digit_limit == 0:
        pytest.skip("interpreter integer string limit disabled")
    output = '{"artifacts":{"result.json":{"n":' + ("1" * (digit_limit + 1)) + "}}}"
    row = _run_returned_output(tmp_path, output)
    diagnostics = row["output_diagnostics"]
    assert diagnostics["parser"]["status"] == "json_value_error"
    assert "json_value_error" in diagnostics["codes"]
    assert "duplicate_key_rejected" not in diagnostics["codes"]


def test_json_artifact_nan_reports_serialization_failure(tmp_path):
    row = _run_returned_output(tmp_path, '{"artifacts":{"result.json":{"n":NaN}}}')
    diagnostics = row["output_diagnostics"]
    assert "artifact_serialization_failed" in diagnostics["codes"]
    assert diagnostics["artifact_comparison"]["status"] == "serialization_failed"
    assert diagnostics["artifact_comparison"]["mismatched_artifacts"] == ["result.json"]


@pytest.mark.parametrize(("artifact_name", "output"), [
    ("result.json", '{"artifacts":{"result.json":{"text":"\\ud800"}}}'),
    ("result.md", '{"artifacts":{"result.md":"\\ud800"}}'),
])
def test_lone_surrogate_reports_utf8_encoding_failure_without_text(tmp_path, artifact_name, output):
    row = _run_returned_output(tmp_path, output, expected=(artifact_name,))
    diagnostics = row["output_diagnostics"]
    assert "artifact_encoding_failed" in diagnostics["codes"]
    assert diagnostics["artifact_comparison"]["status"] == "encoding_failed"
    assert diagnostics["artifact_comparison"]["mismatched_artifacts"] == [artifact_name]
    assert diagnostics["artifact_comparison"]["encoding_error_type"] == "UnicodeEncodeError"
    assert "\\ud800" not in json.dumps(diagnostics)


def test_extra_artifact_diagnostic_counts_without_reflecting_model_name(tmp_path):
    output = '{"artifacts":{"result.json":{},"sk_live_synthetic_secret_marker.json":{}}}'
    row = _run_returned_output(tmp_path, output)
    diagnostics = row["output_diagnostics"]
    assert diagnostics["artifact_comparison"]["extra_artifact_count"] == 1
    assert "extra_artifacts" not in diagnostics["artifact_comparison"]
    assert "sk_live_synthetic_secret_marker" not in json.dumps(diagnostics)


def test_wellformed_returned_output_has_no_malformed_diagnostics(tmp_path):
    row = _run_returned_output(tmp_path, '{"artifacts":{"result.json":{}}}', expected=("result.json",))
    assert (row["execution_state"], row["receipt_state"]) == ("returned", "verified")
    assert "output_diagnostics" not in row


@pytest.mark.parametrize(("artifact_name", "output"), [
    ("result.json", '{"artifacts":{"result.json":{"text":"é"}}}'),
    ("result.md", '{"artifacts":{"result.md":"é"}}'),
])
def test_valid_unicode_output_has_no_malformed_diagnostics(tmp_path, artifact_name, output):
    row = _run_returned_output(tmp_path, output, expected=(artifact_name,))
    assert (row["execution_state"], row["receipt_state"]) == ("returned", "verified")
    assert "output_diagnostics" not in row
