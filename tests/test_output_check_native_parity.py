from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.output_check_gateway import authority_data_ref
from harness.output_check_service import OutputCheckError, run_output_check_operation


SOURCE = "irs-2025-tax-table-single"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace(tmp_path: Path, answer_value=4169) -> dict:
    checker = tmp_path / "tax_authority.py"
    marker = tmp_path / "checker-ran.txt"
    checker.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'value': 4169}))\n",
        encoding="utf-8",
    )
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "fields": [{"name": "tax", "authority": "TABLE", "source": SOURCE,
                    "describes": "Form 1040 line 16"}],
        "authorities": {SOURCE: {"kind": "command",
                                 "argv": [sys.executable, "tax_authority.py"]}},
    }), encoding="utf-8")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({
        "taxable_income": {"value": 36700, "source": "the return"},
        "tax": {"value": answer_value, "source": SOURCE},
    }), encoding="utf-8")
    return {"contract": contract, "answer": answer, "checker": checker,
            "marker": marker}


def _file(path: Path, root: Path) -> dict:
    return {"kind": "workspace-file",
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path)}


def _operation(root: Path, files: dict, **extra) -> dict:
    contract = _file(files["contract"], root)
    answer = _file(files["answer"], root)
    source_paths = files["authority_sources"] if "authority_sources" in files else [
        files["checker"]]
    authority_sources = [_file(path, root) for path in source_paths]
    op = {
        "contract": contract,
        "answer": answer,
        "authority_sources": authority_sources,
        "allow_commands": False,
        "strict": False,
        "json": True,
        "stream": False,
        "data_refs": [
            f"data_output_check.contract:{contract['sha256'][:32]}",
            f"data_output_check.answer:{answer['sha256'][:32]}",
            *(authority_data_ref(source, index)
              for index, source in enumerate(authority_sources)),
        ],
        "credential_refs": [],
    }
    op.update(extra)
    return op


def test_output_check_operation_shape_is_exact_and_scope_derived(tmp_path):
    files = _workspace(tmp_path)
    op = canonicalize_operation("output.check", _operation(
        tmp_path, files, allow_commands=True,
        report={"kind": "run-artifact", "path": "reports/check.json"}))
    assert op.destination == {"kind": "output-check",
                              "ref": op.operation["contract"]["sha256"][:16]}
    assert op.scopes == ("write", "exec")
    assert canonicalize_operation("output.check", _operation(
        tmp_path, files)).scopes == ()
    assert canonicalize_operation("output.check", _operation(
        tmp_path, files, verify_lean=True)).scopes == ("write", "exec")
    with pytest.raises(GatewayOperationError):
        canonicalize_operation("output.check", {
            **_operation(tmp_path, files), "allow_command": True})
    with pytest.raises(GatewayOperationError):
        canonicalize_operation("output.check", {
            **_operation(tmp_path, files), "authority_sources": []})


def test_native_service_matches_cli_for_granted_command_authority(tmp_path):
    files = _workspace(tmp_path)
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=True),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "PASS"
    assert result["release"] == "RELEASE"
    assert result["cli_exit_code"] == 0
    assert result["normal_exit_code"] == 0
    assert files["marker"].read_text(encoding="utf-8") == "ran"


def test_native_service_without_command_grant_never_runs_or_passes(tmp_path):
    files = _workspace(tmp_path)
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=False),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "UNVERIFIABLE"
    assert result["cli_exit_code"] == 3
    assert not files["marker"].exists()


def test_native_service_report_withholds_authoritative_value(tmp_path):
    files = _workspace(tmp_path, answer_value=4165.50)
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=True,
                   report={"kind": "run-artifact",
                           "path": "reports/output-check.json"}),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "FAIL"
    assert result["cli_exit_code"] == 1
    assert "4169" not in result["stdout_text"]
    assert "4169" not in result["stdout_json"]
    report = result["artifacts"]["report"]
    assert report["path"] == "reports/output-check.json"
    assert "4169" not in (tmp_path / "run" / report["path"]).read_text(
        encoding="utf-8")


def test_native_service_redacts_command_authority_diagnostics(tmp_path):
    files = _workspace(tmp_path)
    checker = files["contract"].parent / "tax_authority.py"
    checker.write_text(
        "import sys\n"
        "print('expected 4169', file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=True,
                   report={"kind": "run-artifact",
                           "path": "reports/output-check.json"}),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "UNVERIFIABLE"
    assert "4169" not in result["stdout_text"]
    assert "4169" not in result["stdout_json"]
    assert "4169" not in json.dumps(result["fields"])
    report = result["artifacts"]["report"]
    assert "4169" not in (tmp_path / "run" / report["path"]).read_text(
        encoding="utf-8")


def test_native_service_parses_the_bytes_that_matched_digest(monkeypatch, tmp_path):
    files = _workspace(tmp_path)
    answer_path = files["answer"]
    operation = _operation(tmp_path, files, allow_commands=True)
    original = Path.read_bytes
    changed = {"done": False}

    def read_bytes(path):
        data = original(path)
        if Path(path) == answer_path and not changed["done"]:
            changed["done"] = True
            answer_path.write_text(json.dumps({
                "taxable_income": {"value": 36700, "source": "the return"},
                "tax": {"value": 0, "source": SOURCE},
            }), encoding="utf-8")
        return data

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    result = run_output_check_operation(
        operation, repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert changed["done"] is True
    assert result["verdict"] == "PASS"


def test_native_service_refuses_digest_drift_before_checker_runs(tmp_path):
    files = _workspace(tmp_path)
    op = _operation(tmp_path, files, allow_commands=True)
    op["answer"] = {**op["answer"], "sha256": "0" * 64}
    with pytest.raises(OutputCheckError) as exc:
        run_output_check_operation(
            op, repo_root=tmp_path, run_root=tmp_path / "run",
            state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert exc.value.code == "SOURCE_DRIFT"
    assert not files["marker"].exists()


def test_native_strict_exit_keeps_lean_verification_failure(monkeypatch, tmp_path):
    files = _workspace(tmp_path)

    def fail_lean(source, path, *, lean=None):
        del lean
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return {"verdict": "FAIL", "checker": "", "axioms": [],
                "errors": ["simulated"], "file": str(path),
                "reason": "simulated kernel failure"}

    monkeypatch.setattr("harness.output_check_service.prove", fail_lean)
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=True, strict=True,
                   verify_lean=True),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32,
        operation_ref="op_" + "c" * 32)
    assert result["verdict"] == "PASS"
    assert result["release"] == "RELEASE"
    assert result["normal_exit_code"] == 1
    assert result["strict_exit_code"] == 1
    assert result["cli_exit_code"] == 1
    assert result["artifacts"]["lean"]["path"] == (
        "output-check/op_" + "c" * 32 + "/Answer.lean")


def test_native_default_ledger_is_operation_scoped_and_contained(tmp_path):
    files = _workspace(tmp_path)
    result = run_output_check_operation(
        _operation(tmp_path, files, allow_commands=True, scope="task"),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32,
        operation_ref="op_" + "d" * 32)
    assert result["artifacts"]["ledger"]["path"] == (
        "output-check/op_" + "d" * 32 + "/validation.jsonl")
