import hashlib
import json

from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path, value, *, raw=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if raw else json.dumps(value), encoding="utf-8")


def _sync(raw, report, md_path):
    _write(raw, {"artifacts": {"report.json": report,
                                "report.md": md_path.read_bytes().decode("utf-8")}})


def test_hidden_oracle_fixture_split_preserves_visible_input_hashes(tmp_path):
    workspace, oracle_root, attempt = tmp_path / "workspace", tmp_path / "oracle", tmp_path / "attempt"
    workspace.mkdir(); oracle_root.mkdir(); attempt.mkdir()
    visible = {"measurements": [{"measurement_id": "m1", "value": 2,
                                  "denominator": 4, "interval_95": [0.1, 0.9]}],
               "claims": [{"claim_id": "c1", "text": "The value is 2."}]}
    hidden = json.loads(json.dumps(visible)); hidden["claims"][0]["supported_by"] = ["m1"]
    _write(workspace / "visible.json", visible); _write(oracle_root / "hidden.json", hidden)
    visible_hashes = {"visible.json": _sha((workspace / "visible.json").read_bytes())}
    oracle_hashes = {"hidden.json": _sha((oracle_root / "hidden.json").read_bytes())}
    report = {"task_id": "lfh-015-evidence-bound-nonleaky", "input_sha256s": visible_hashes,
              "measurements": visible["measurements"],
              "claim_verdicts": [{"claim_id": "c1", "verdict": "supported", "evidence": ["m1"]}]}
    json_path, md_path, raw = attempt / "report.json", attempt / "report.md", attempt / "output.txt"
    _write(json_path, report); _write(md_path, "# lfh-015-evidence-bound-nonleaky\n", raw=True)
    _sync(raw, report, md_path)
    core = {"workspace_root": str(workspace), "oracle_root": str(oracle_root),
            "attempt_dir": str(attempt), "raw_prompt_sha256": "a" * 64,
            "tool_policy_sha256": "b" * 64, "raw_artifact_sha256": _sha(raw.read_bytes()),
            "receipt_sha256": "c" * 64, "orthogonal_states": {"execution_state": "returned",
            "oracle_state": "not_run", "receipt_state": "not_emitted"}}
    context = OracleContext("lfh-015-evidence-bound-nonleaky",
        {"checker_id": "evidence_bound_reporting/v1", "fixture": "hidden.json",
         "expected_artifacts": ["report.json", "report.md"]}, raw,
        {"report.json": json_path, "report.md": md_path}, visible_hashes, core,
        visible_input_sha256s=visible_hashes, oracle_input_sha256s=oracle_hashes)

    result = evaluate_task_oracle(context)

    roles = {row["role"] for row in result.checked_artifacts}
    assert result.state == "pass"
    assert roles >= {"raw_output", "oracle_fixture", "provider:report.json", "provider:report.md"}
    assert "input_fixture" not in roles
