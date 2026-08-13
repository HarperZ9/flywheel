import json

import pytest

from harness import cli_entry
from harness.evidence_cli import main
from harness.evidence_journey import append_event, new_journey, run_journey_check


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _journey():
    journey = new_journey(journey_id="cli-journey", goal="Explain the failure",
        intake={"summary": "failed"}, created_at="2026-08-12T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-12T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The check failed",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "checker has not run", "receipt_refs": []}]})


def _run(capsys, root, *args):
    code = main(list(args), root=root)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_cli_start_and_project_emit_one_json_document(tmp_path, capsys):
    _write(tmp_path / "intake.json", {"summary": "failed"})
    code, started, err = _run(capsys, tmp_path, "start", "--journey-id", "j-1",
        "--goal", "Explain", "--created-at", "2026-08-12T12:00:00Z",
        "--intake-ref", "intake.json")
    assert code == 0 and err == "" and started["journey_id"] == "j-1"
    _write(tmp_path / "journey.json", _journey())
    code, view, err = _run(capsys, tmp_path, "project",
        "--journey-ref", "journey.json", "--lens", "Diagnose")
    assert code == 0 and err == "" and view["lens"] == "Diagnose"


def test_cli_check_has_exact_unverifiable_exit_and_no_receipt(tmp_path, capsys):
    _write(tmp_path / "journey.json", _journey())
    _write(tmp_path / "context.json", {"task_id": "cli", "prompt": "Check",
        "oracle_cmd": "python -m pytest test_candidate.py",
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 5})
    code, result, err = _run(capsys, tmp_path, "check",
        "--journey-ref", "journey.json", "--claim-id", "claim-root",
        "--oracle-id", "code", "--candidate-ref", "candidate.py",
        "--context-ref", "context.json")
    assert code == 4 and err == ""
    assert result["unverifiable_reason"] == "EXECUTION_CONTAINMENT_UNAVAILABLE"
    assert "receipt_ref" not in result and not (tmp_path / "receipts").exists()


def _checked_measurement(root):
    journey = _journey()
    candidate = root / "measurement.json"
    _write(candidate, {"effect": 0.1, "ci_low": 0.05, "ci_high": 0.15,
        "min_effect": 0.2, "n": 10,
        "negative_control": {"effect": 0, "ci_low": -0.1, "ci_high": 0.1}})
    context = {"task_id": "cli", "prompt": "Check measurement",
        "oracle_cmd": "measurement-gate", "candidate_ref": candidate.name,
        "raw_artifact_refs": [candidate.name], "timeout_seconds": 5}
    check = run_journey_check(journey, "claim-root", "ml", candidate, context)
    claim = {**journey["events"][-1]["claims"][0], "verdict": check["verdict"],
             "receipt_refs": [check["receipt_ref"]],
             "raw_artifact_refs": check["raw_artifact_refs"]}
    return append_event(journey, {"stage": "preflight",
        "occurred_at": "2026-08-12T12:02:00Z", "claims": [claim]})


def test_cli_export_and_recheck_preserve_unsigned_then_anchored_states(tmp_path, capsys):
    _write(tmp_path / "journey.json", _checked_measurement(tmp_path))
    code, exported, err = _run(capsys, tmp_path, "export",
        "--journey-ref", "journey.json", "--packet-ref", "packet")
    assert code == 4 and err == "" and exported["structural_verdict"] == "MATCH"
    code, checked, err = _run(capsys, tmp_path, "recheck",
        "--packet-ref", "packet", "--expected-manifest-sha256", exported["packet_sha256"])
    assert code == 0 and err == "" and checked["verdict"] == "MATCH"


def test_cli_transport_error_is_exact_exit_two_and_json_stdout(tmp_path, capsys):
    _write(tmp_path / "journey.json", _journey())
    code, result, err = _run(capsys, tmp_path, "project",
        "--journey-ref", "journey.json", "--lens", "Score")
    assert code == 2 and err == ""
    assert result["schema"] == "flywheel.evidence-transport-error/v1"
    assert result["error"]["code"] == "UNSUPPORTED_LENS"


def test_cli_rejects_inline_evidence_arguments(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["start", "--journey-id", "j", "--goal", "g",
              "--created-at", "2026-08-12T12:00:00Z",
              "--intake-ref", "intake.json",
              "--intake-json", '{"secret":"raw"}'])
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert captured.err == "" and result["error"]["code"] == "INVALID_ARGUMENTS"
    assert "raw" not in captured.out


def test_cli_missing_argument_is_json_stdout_without_usage_or_traceback(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["project", "--journey-ref", "journey.json"])
    captured = capsys.readouterr()
    assert stopped.value.code == 2 and captured.err == ""
    result = json.loads(captured.out)
    assert result["error"]["code"] == "INVALID_ARGUMENTS"
    assert "usage:" not in captured.out.lower() and "traceback" not in captured.out.lower()


def test_cli_entry_dispatches_journey_without_repo_resolution(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_entry, "find_repo_root",
                        lambda: pytest.fail("packaged journey consulted a checkout"))
    with pytest.raises(SystemExit) as stopped:
        cli_entry.main(["journey", "--help"])
    assert stopped.value.code == 0
    out = capsys.readouterr().out
    assert "start" in out and "recheck" in out


@pytest.mark.parametrize("verdict,expected", [
    ("PASS", 0), ("MATCH", 0), ("FAIL", 1), ("DRIFT", 1),
    ("UNDECIDED", 3), ("UNVERIFIABLE", 4),
])
def test_cli_verdict_exit_contract(verdict, expected):
    from harness.evidence_cli import result_exit
    assert result_exit({"verdict": verdict}, http_status=200, action="recheck") == expected
