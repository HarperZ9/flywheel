from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from harness.output_check_gateway import authority_data_ref
from harness.output_check_service import OutputCheckError, run_output_check_operation


SOURCE = "irs-2025-tax-table-single"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file(path: Path, root: Path) -> dict:
    return {"kind": "workspace-file",
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path)}


def _operation(root: Path, contract: Path, answer: Path, sources: list[Path],
               **extra) -> dict:
    contract_ref, answer_ref = _file(contract, root), _file(answer, root)
    source_refs = [_file(path, root) for path in sources]
    op = {"contract": contract_ref, "answer": answer_ref,
          "authority_sources": source_refs, "allow_commands": False,
          "strict": False, "json": True, "stream": False,
          "data_refs": [
              f"data_output_check.contract:{contract_ref['sha256'][:32]}",
              f"data_output_check.answer:{answer_ref['sha256'][:32]}",
              *(authority_data_ref(source, index)
                for index, source in enumerate(source_refs)),
          ], "credential_refs": []}
    op.update(extra)
    return op


def _table_workspace(tmp_path: Path, *, row_value=4169,
                     answer_value=4169) -> tuple[Path, Path, Path]:
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps({"36700": row_value}), encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "fields": [{"name": "tax", "authority": "TABLE", "source": SOURCE}],
        "authorities": {SOURCE: {"kind": "table", "path": "rows.json",
                                 "key_field": "taxable_income"}},
    }), encoding="utf-8")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({
        "taxable_income": {"value": 36700, "source": "the return"},
        "tax": {"value": answer_value, "source": SOURCE},
    }), encoding="utf-8")
    return contract, answer, rows


def _command_workspace(tmp_path: Path, *,
                       helper_value=4169) -> tuple[Path, Path, Path, Path]:
    marker = tmp_path / "checker-ran.txt"
    checker = tmp_path / "tax_authority.py"
    checker.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
        "json.load(sys.stdin)\n"
        f"print(json.dumps({{'value': {helper_value}}}))\n",
        encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "fields": [{"name": "tax", "authority": "TABLE", "source": SOURCE}],
        "authorities": {SOURCE: {"kind": "command",
                                 "argv": [sys.executable, "tax_authority.py"]}},
    }), encoding="utf-8")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({
        "taxable_income": {"value": 36700, "source": "the return"},
        "tax": {"value": 4169, "source": SOURCE},
    }), encoding="utf-8")
    return contract, answer, checker, marker


def test_native_service_uses_unchanged_table_authority_source(tmp_path):
    contract, answer, rows = _table_workspace(tmp_path)
    result = run_output_check_operation(
        _operation(tmp_path, contract, answer, [rows]),
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "PASS"
    assert result["release"] == "RELEASE"


def test_native_service_refuses_table_authority_source_drift_before_pass(tmp_path):
    contract, answer, rows = _table_workspace(
        tmp_path, row_value=0, answer_value=4169)
    operation = _operation(tmp_path, contract, answer, [rows])
    rows.write_text(json.dumps({"36700": 4169}), encoding="utf-8")
    with pytest.raises(OutputCheckError) as exc:
        run_output_check_operation(
            operation, repo_root=tmp_path, run_root=tmp_path / "run",
            state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert exc.value.code == "SOURCE_DRIFT"


def test_native_service_uses_pinned_table_after_path_replacement(
        monkeypatch, tmp_path):
    contract, answer, rows = _table_workspace(
        tmp_path, row_value=0, answer_value=4169)
    operation = _operation(tmp_path, contract, answer, [rows])
    from harness import output_check_service as service
    real_pin = service.pinned_authority_sources

    def pin_then_replace(*args, **kwargs):
        pinned = real_pin(*args, **kwargs)
        rows.write_text(json.dumps({"36700": 4169}), encoding="utf-8")
        return pinned

    monkeypatch.setattr(service, "pinned_authority_sources", pin_then_replace)
    result = run_output_check_operation(
        operation, repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "FAIL"
    assert result["release"] == "HOLD"


def test_native_service_refuses_command_authority_source_drift_before_run(tmp_path):
    contract, answer, checker, marker = _command_workspace(tmp_path)
    operation = _operation(
        tmp_path, contract, answer, [checker], allow_commands=True)
    checker.write_text("print('{\"value\": 4169}')\n", encoding="utf-8")
    with pytest.raises(OutputCheckError) as exc:
        run_output_check_operation(
            operation, repo_root=tmp_path, run_root=tmp_path / "run",
            state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert exc.value.code == "SOURCE_DRIFT"
    assert not marker.exists()


def test_native_service_uses_pinned_command_helper_after_path_replacement(
        monkeypatch, tmp_path):
    contract, answer, checker, marker = _command_workspace(
        tmp_path, helper_value=0)
    operation = _operation(
        tmp_path, contract, answer, [checker], allow_commands=True)
    from harness import output_check_service as service
    real_pin = service.pinned_authority_sources

    def pin_then_replace(*args, **kwargs):
        pinned = real_pin(*args, **kwargs)
        checker.write_text(
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text('new')\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'value': 4169}))\n",
            encoding="utf-8")
        return pinned

    monkeypatch.setattr(service, "pinned_authority_sources", pin_then_replace)
    result = run_output_check_operation(
        operation, repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "FAIL"
    assert result["release"] == "HOLD"
    assert marker.read_text(encoding="utf-8") == "ran"


def test_native_service_runs_command_authority_from_pinned_copy(
        monkeypatch, tmp_path):
    contract, answer, checker, marker = _command_workspace(tmp_path)
    operation = _operation(
        tmp_path, contract, answer, [checker], allow_commands=True)
    from harness import authority_registry
    real_run = authority_registry.subprocess.run

    def mutate_original_then_run(argv, **kwargs):
        checker.write_text(
            "import json\nprint(json.dumps({'value': 0}))\n",
            encoding="utf-8")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(authority_registry.subprocess, "run",
                        mutate_original_then_run)
    result = run_output_check_operation(
        operation, repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state", owner_ref="owner_" + "a" * 32)
    assert result["verdict"] == "PASS"
    assert result["release"] == "RELEASE"
    assert marker.read_text(encoding="utf-8") == "ran"
