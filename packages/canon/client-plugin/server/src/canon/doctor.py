from __future__ import annotations
from dataclasses import dataclass
from typing import TextIO
from .adapter import AdapterDescriptor, descriptor_for, validate_adapter_descriptor
from .atom import CanonAtom, validate_atom
from .bootstrap_sources import (
    DoctorConfig,
    DoctorConfigError,
    DoctorFinding,
    DoctorReport,
    DOCTOR_FAILURE_PRIORITY,
    SourceParseError,
    snapshot_doctor_config,
    strict_jsonl_objects,
    utf8_text,
)
from .canonical_json import canonical_sha256, sha256_text
from .cli_artifacts import ArtifactError, SourceBytes, checked_workspace, read_source_file
from .cli_compile import CompileCliError, _stdin_source
from .cli_format import make_result, write_result
from .schema import Record
from .secret_quarantine import scan_text
from .source_state import SourceStateError, assert_source_state, source_state_sha256
from .validator import validate_record

@dataclass(frozen=True, slots=True)
class _Source:
    role: str
    bytes: SourceBytes
    text: str

def run_doctor(config: DoctorConfig) -> DoctorReport:
    try:
        snapshot = snapshot_doctor_config(config)
    except DoctorConfigError:
        return _invalid_config_report()
    findings: list[DoctorFinding] = []
    descriptor = _load_descriptor(snapshot["target"], findings)
    workspace = _workspace(snapshot["workspace"], findings)
    sources = _load_sources(snapshot, workspace, findings) if workspace is not None else ()
    _scan_sources(sources, findings)
    digest = _source_state_digest(sources, findings)
    if not _has_blocker(findings, {"secret_quarantine"}):
        _check_expected(snapshot["expected_source_state"], sources, findings)
    if not _has_blocker(findings, {"secret_quarantine", "source_changed"}):
        _validate_sources(sources, findings)
    if snapshot["offline"] is True:
        findings.append(_offline_unknown())
    return _report(findings, sources, digest, descriptor, bool(snapshot["offline"]))

def run_doctor_command(parsed: object, *, stdin: TextIO | None, stdout: TextIO, stderr: TextIO, color: bool) -> int:
    try:
        config = DoctorConfig(workspace=parsed.workspace, target=parsed.target,
                              records=parsed.records, atoms=parsed.atoms,
                              offline=parsed.offline,
                              expected_source_state=parsed.expected_source_state,
                              stdin_source=_cli_stdin_source(parsed, stdin))
        report = run_doctor(config)
    except (CompileCliError, DoctorConfigError):
        report = _invalid_config_report()
    result = make_result(ok=report.ok, command="doctor", failure_code=report.failure_code,
                         message=report.message, data=report.to_result_data())
    return write_result(result, stdout=stdout, stderr=stderr, json_output=parsed.json_output, color=color)

def _load_descriptor(target: object, findings: list[DoctorFinding]) -> AdapterDescriptor | None:
    try:
        descriptor = descriptor_for(target)  # type: ignore[arg-type]
    except KeyError:
        findings.append(_finding("adapter_unknown", "blocker", "invalid_args", "unsupported doctor target"))
        return None
    if validate_adapter_descriptor(descriptor):
        findings.append(_finding("adapter_descriptor_invalid", "blocker", "invalid_args", "adapter descriptor invalid"))
    elif descriptor.integration_tier == "unsupported":
        findings.append(_finding("unsupported_lifecycle", "blocker", "unsupported_lifecycle", "unsupported doctor target"))
    else:
        data = {"adapter_id": descriptor.adapter_id, "integration_tier": descriptor.integration_tier}
        findings.append(_finding("adapter_descriptor_valid", "info", "ok", "adapter descriptor valid", data))
    return descriptor

def _workspace(path: object, findings: list[DoctorFinding]):
    try:
        return checked_workspace(path)
    except ArtifactError as exc:
        findings.append(_finding("workspace_unavailable", "blocker", _artifact_code(exc), "doctor workspace unavailable"))
        return None

def _load_sources(snapshot: dict[str, object], workspace: object, findings: list[DoctorFinding]) -> tuple[_Source, ...]:
    loaded: list[_Source] = []
    for role in ("records", "atoms"):
        raw = snapshot[role]
        if raw is None:
            continue
        try:
            source = _source_for(role, raw, snapshot, workspace)
            loaded.append(_Source(role, source, utf8_text(source.data)))
        except SourceParseError:
            findings.append(_source_finding(role, "invalid_args", "invalid source input"))
        except ArtifactError as exc:
            findings.append(_source_finding(role, _artifact_code(exc), "doctor source unavailable"))
        except (CompileCliError, DoctorConfigError):
            findings.append(_source_finding(role, "invalid_args", "invalid source input"))
    return tuple(loaded)

def _source_for(role: str, raw: object, snapshot: dict[str, object], workspace: object) -> SourceBytes:
    if raw == "-":
        source = snapshot["stdin_source"]
        if type(source) is not SourceBytes or source.path != f"stdin-{role}":
            raise DoctorConfigError("invalid doctor config")
        return source
    return read_source_file(raw, workspace=workspace)  # type: ignore[arg-type]

def _scan_sources(sources: tuple[_Source, ...], findings: list[DoctorFinding]) -> None:
    for source in sources:
        got = tuple(scan_text(source.bytes.path, source_id=f"{source.role}-path"))
        got += tuple(scan_text(source.text, source_id=source.role))
        if got:
            findings.append(_secret_finding(source.role, got))

def _source_state_digest(sources: tuple[_Source, ...], findings: list[DoctorFinding]) -> str:
    try:
        digest = source_state_sha256(tuple(source.bytes.item() for source in sources))
    except SourceStateError:
        findings.append(_finding("source_state_invalid", "blocker", "invalid_args", "invalid source state"))
        return source_state_sha256(())
    findings.append(_finding("source_state_bound", "info", "ok", "source state bound", {"source_count": len(sources)}))
    return digest

def _check_expected(expected: object, sources: tuple[_Source, ...], findings: list[DoctorFinding]) -> None:
    if expected is None:
        return
    try:
        assert_source_state(expected, tuple(source.bytes.item() for source in sources))  # type: ignore[arg-type]
    except SourceStateError as exc:
        code = "source_changed" if exc.code == "source_changed" else "invalid_args"
        findings.append(_finding(code, "blocker", code, "source state changed"))

def _validate_sources(sources: tuple[_Source, ...], findings: list[DoctorFinding]) -> None:
    for source in sources:
        count = _validate_source(source, findings)
        if count is not None:
            data = {"count": count, "source": source.role}
            findings.append(_finding(f"{source.role}_valid", "info", "ok", f"{source.role} valid", data))

def _validate_source(source: _Source, findings: list[DoctorFinding]) -> int | None:
    try:
        lines = strict_jsonl_objects(source.bytes.data)
    except SourceParseError as exc:
        findings.append(_source_finding(source.role, "invalid_args", "invalid source input", line=exc.line))
        return None
    count = 0
    for item in lines:
        try:
            obj = Record.from_dict(item.value) if source.role == "records" else CanonAtom.from_dict(item.value)
            problems = validate_record(obj) if source.role == "records" else validate_atom(obj)
        except (KeyError, TypeError, ValueError):
            findings.append(_source_finding(source.role, "invalid_args", "invalid source input", line=item.line))
            return None
        if problems:
            findings.append(_source_finding(source.role, "invalid_args", "invalid source input", line=item.line))
            return None
        count += 1
    return count

def _report(findings: list[DoctorFinding], sources: tuple[_Source, ...], digest: str,
            descriptor: AdapterDescriptor | None, offline: bool) -> DoctorReport:
    ordered = tuple(item[1] for item in sorted(enumerate(findings), key=lambda item: (_priority(item[1]), item[0])))
    blockers = [finding for finding in ordered if finding.severity == "blocker"]
    failure_code = blockers[0].failure_code if blockers else "ok"
    data = {"offline": offline, "source_inputs": [_safe_label(source) for source in sources],
            "source_state_sha256": digest, "target": _target_data(descriptor)}
    return DoctorReport(failure_code == "ok", failure_code, "doctor diagnostics complete", ordered, data)

def _invalid_config_report() -> DoctorReport:
    finding = _finding("invalid_config", "blocker", "invalid_args", "invalid doctor config")
    return DoctorReport(False, "invalid_args", "invalid doctor config", (finding,), {"offline": False, "source_inputs": []})

def _finding(code: str, severity: str, failure_code: str, message: str, evidence: dict[str, object] | None = None) -> DoctorFinding:
    return DoctorFinding(code, severity, failure_code, message, evidence or {})

def _source_finding(role: str, failure_code: str, message: str, *, line: int | None = None) -> DoctorFinding:
    evidence: dict[str, object] = {"source": role}
    if line is not None:
        evidence["line"] = line
    return _finding(failure_code, "blocker", failure_code, message, evidence)

def _secret_finding(role: str, findings: tuple[object, ...]) -> DoctorFinding:
    codes = sorted({getattr(finding, "code", "secret") for finding in findings})
    data = {"codes": codes, "count": len(findings),
            "metadata_sha256": canonical_sha256({"codes": codes, "count": len(findings), "source": role}),
            "source": role}
    return _finding("secret_quarantine", "blocker", "secret_quarantine", "source quarantined", data)

def _offline_unknown() -> DoctorFinding:
    data = {"does_not_prove": "Offline doctor performs no remote/provider reachability check.", "status": "unknown"}
    return _finding("remote_reachability_unknown", "info", "ok", "remote reachability unknown", data)

def _target_data(descriptor: AdapterDescriptor | None) -> dict[str, object] | None:
    if descriptor is None:
        return None
    return {"adapter_id": descriptor.adapter_id, "bootstrap": descriptor.bootstrap,
            "display_name": descriptor.display_name, "integration_tier": descriptor.integration_tier,
            "known_unknowns": list(descriptor.known_unknowns), "target_surfaces": list(descriptor.target_surfaces)}

def _cli_stdin_source(parsed: object, stdin: TextIO | None) -> SourceBytes | None:
    roles = [role for role in ("records", "atoms") if getattr(parsed, role) == "-"]
    if len(roles) > 1:
        raise CompileCliError("invalid_args")
    return None if not roles else _stdin_source(stdin, roles[0])

def _artifact_code(exc: ArtifactError) -> str:
    return exc.code if type(exc.code) is str else "invalid_args"

def _safe_label(source: _Source) -> str:
    if scan_text(source.bytes.path, source_id=f"{source.role}-path"):
        return source.role + ":" + sha256_text(source.bytes.path).removeprefix("sha256:")[:16]
    return source.bytes.path

def _priority(finding: DoctorFinding) -> int:
    return 100 if finding.severity != "blocker" else DOCTOR_FAILURE_PRIORITY[finding.failure_code]

def _has_blocker(findings: list[DoctorFinding], codes: set[str]) -> bool:
    return any(finding.severity == "blocker" and finding.failure_code in codes for finding in findings)

__all__ = ["DoctorConfig", "DoctorConfigError", "DoctorFinding", "DoctorReport", "run_doctor"]
