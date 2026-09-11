"""Shared native service for flywheel check-output."""
from __future__ import annotations

import json
from pathlib import Path

from .answer_docs import DocumentError, from_latex, from_markdown, from_pdf
from .contract_terms import HOLD
from .output_check_cli import EXIT, SEVERITY, check, specs
from .output_check_sources import (
    OutputCheckError,
    command_custody_contract,
    pinned_authority_sources,
    run_artifact as _artifact,
    sha256_bytes as _sha,
    source_file as _source,
    workspace_dir as _dir,
)
from .proof_lean import lean_source
from .proof_relations import RelationError
from .proof_run import prove
from .report_docs import as_text, write_report
from .validation_ledger import TASK, record


def _artifact_doc(path: Path, run_root: Path) -> dict:
    rel = path.resolve().relative_to(run_root.resolve()).as_posix()
    return {"kind": "run-artifact", "path": rel, "sha256": _sha(path.read_bytes()),
            "bytes": path.stat().st_size}


def _default_artifact(name: str, run_root: Path, operation_ref: str) -> Path:
    return _artifact({"kind": "run-artifact",
                      "path": f"output-check/{operation_ref}/{name}"}, run_root)


def _answer_from_bytes(path: Path, data: bytes) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return from_pdf(data)
    text = data.decode("utf-8")
    if suffix in (".md", ".markdown"):
        return from_markdown(text)
    if suffix in (".tex", ".latex"):
        return from_latex(text)
    if suffix == ".json":
        value = json.loads(text)
        if not isinstance(value, dict):
            raise DocumentError("an answer is an object of fields")
        return value
    raise DocumentError(f"no reader for {suffix or 'a file with no suffix'}")


def _redact_command_diagnostics(report: dict, contract_doc: dict) -> None:
    authorities = contract_doc.get("authorities") or {}
    command_sources = {source for source, spec in authorities.items()
                       if type(spec) is dict and spec.get("kind") == "command"}
    for container in (report.get("fields", ()),
                      report.get("next", {}).get("fields", ())):
        for row in container:
            if (type(row) is dict and row.get("source") in command_sources
                    and row.get("verdict") != "PASS"):
                row["reason"] = (
                    f"{row['source']} command diagnostics were withheld")


def _exit(report: dict, *, strict: bool, verify_lean: bool) -> tuple[int, int]:
    verdict = report["verdict"]
    if verify_lean and SEVERITY[report["proof"]["verdict"]] > SEVERITY[verdict]:
        verdict = report["proof"]["verdict"]
    normal = EXIT[verdict]
    strict_exit = normal
    if report["release"] != "RELEASE":
        strict_exit = 1 if report["release"] == HOLD else 3
    return (strict_exit if strict else normal), strict_exit


def _proof(operation: dict, contract_doc: dict, report: dict, answer: dict,
           *, base_dir: Path, repo_root: Path, run_root: Path,
           operation_ref: str,
           pinned_sources: dict[Path, bytes]) -> tuple[dict, dict]:
    if not operation.get("lean") and not operation.get("verify_lean"):
        return {}, {}
    lean_path = (_artifact(operation["lean"], run_root)
                 if operation.get("lean") else _default_artifact(
                     "Answer.lean", run_root, operation_ref))
    try:
        source = lean_source(report, answer, specs(
            contract_doc, base_dir=base_dir, pinned_sources=pinned_sources),
            relations=contract_doc.get("relations") or ())
    except RelationError as exc:
        raise OutputCheckError(f"INVALID_REQUEST:{exc}") from None
    if operation.get("verify_lean"):
        lean_bin = (_source(operation["lean_bin"], repo_root)[0]
                    if operation.get("lean_bin") else None)
        proof = prove(source, lean_path, lean=str(lean_bin) if lean_bin else None)
    else:
        lean_path.parent.mkdir(parents=True, exist_ok=True)
        lean_path.write_text(source, encoding="utf-8")
        proof = {"verdict": "UNVERIFIABLE", "checker": "", "axioms": [],
                 "errors": [], "file": str(lean_path),
                 "reason": "written, not checked; pass verify_lean to run the kernel"}
    proof["file"] = _artifact_doc(lean_path, run_root)["path"]
    return proof, {"lean": _artifact_doc(lean_path, run_root)}


def run_output_check_operation(operation: dict, *, repo_root: Path,
                               run_root: Path, state_root: Path,
                               owner_ref: str, operation_ref: str = "manual",
                               progress=None) -> dict:
    del state_root, owner_ref
    repo_root, run_root = Path(repo_root), Path(run_root)
    progress = progress or (lambda _event: None)
    progress({"phase": "reading"})
    contract_path, contract_bytes = _source(operation["contract"], repo_root)
    answer_path, answer_bytes = _source(operation["answer"], repo_root)
    base_dir = _dir(operation["base_dir"], repo_root) if operation.get(
        "base_dir") else contract_path.resolve().parent
    try:
        contract_doc = json.loads(contract_bytes.decode("utf-8"))
        answer = _answer_from_bytes(answer_path, answer_bytes)
    except (DocumentError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise OutputCheckError(f"INVALID_REQUEST:{type(exc).__name__}") from None
    pinned_sources = pinned_authority_sources(
        operation, contract_doc, base_dir=base_dir, repo_root=repo_root)
    check_contract = command_custody_contract(
        contract_doc, base_dir=base_dir, repo_root=repo_root,
        run_root=run_root, operation_ref=operation_ref,
        pinned_sources=pinned_sources)
    progress({"phase": "checking"})
    report = check(check_contract, answer, base_dir=base_dir,
                   allow_commands=operation["allow_commands"],
                   pinned_sources=pinned_sources)
    _redact_command_diagnostics(report, check_contract)
    artifacts: dict[str, dict] = {}
    proof, proof_artifacts = _proof(operation, contract_doc, report, answer,
        base_dir=base_dir, repo_root=repo_root, run_root=run_root,
        operation_ref=operation_ref, pinned_sources=pinned_sources)
    if proof:
        report["proof"] = proof
        artifacts.update(proof_artifacts)
    stdout_json = json.dumps(report, indent=2)
    stdout_text = as_text(report)
    progress({"phase": "writing"})
    if operation.get("out"):
        out = _artifact(operation["out"], run_root)
        out.write_text(stdout_json, encoding="utf-8")
        artifacts["out"] = _artifact_doc(out, run_root)
    if operation.get("report"):
        target = _artifact(operation["report"], run_root)
        write_report(report, target, answer=answer)
        artifacts["report"] = _artifact_doc(target, run_root)
    ledger_entry = None
    if operation.get("ledger") or operation.get("scope", "") or operation.get("subject", ""):
        ledger = (_artifact(operation["ledger"], run_root)
                  if operation.get("ledger") else _default_artifact(
                      "validation.jsonl", run_root, operation_ref))
        ledger_entry = record(report, scope=operation.get("scope") or TASK,
                              subject=operation.get("subject", ""),
                              path=ledger)
        artifacts["ledger"] = _artifact_doc(ledger, run_root)
    cli_exit, strict_exit = _exit(report, strict=operation["strict"],
                                  verify_lean=operation.get("verify_lean", False))
    progress({"phase": "complete", "verdict": report["verdict"],
              "release": report["release"], "cli_exit_code": cli_exit})
    return {"schema": "flywheel.output-check-result/v1",
            "verdict": report["verdict"], "release": report["release"],
            "blocking": report.get("blocking", []),
            "checked": report.get("checked", 0), "passed": report.get("passed", 0),
            "unresolved": report.get("unresolved", []),
            "fields": report.get("fields", []), "next": report.get("next", {}),
            "proof": report.get("proof"), "normal_exit_code": _exit(
                report, strict=False, verify_lean=operation.get("verify_lean", False))[0],
            "strict_exit_code": strict_exit, "cli_exit_code": cli_exit,
            "stdout_text": stdout_text, "stdout_json": stdout_json,
            "artifacts": artifacts, "ledger_entry": ledger_entry}
