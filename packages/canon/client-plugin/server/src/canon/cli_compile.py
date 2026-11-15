from __future__ import annotations

from dataclasses import dataclass
from typing import TextIO

from .adapter import descriptor_for, validate_adapter_descriptor
from .atom import CanonAtom, validate_atom
from .bootstrap_sources import SourceParseError, strict_jsonl_objects, utf8_text
from .canonical_json import canonical_json_text, sha256_bytes, sha256_text
from .capsule import Budget, CapsuleBuildError, CapsuleCompileRequest, CapsuleTarget, SourceState, compile_capsule
from .cli_artifacts import ARTIFACT_NAMES, MAX_SOURCE_BYTES, ArtifactError, SourceBytes, checked_workspace, output_relative, publish_artifacts, read_source_file
from .cli_format import make_result, write_result
from .schema import Record
from .source_state import source_state_sha256
from .secret_quarantine import scan_text
from .validator import validate_record

_BUDGETS = {"needle": 2048, "handoff": 8192, "archive": 32768, "custom": 8192}
_STDIN_CHUNK_CHARS = 65536


class CompileCliError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _LoadedSources:
    records: SourceBytes
    atoms: SourceBytes


def run_compile_command(
    parsed: object,
    *,
    stdin: TextIO | None,
    stdout: TextIO,
    stderr: TextIO,
    color: bool,
) -> int:
    try:
        workspace = checked_workspace(parsed.workspace)  # type: ignore[attr-defined]
        bundle, data = _bundle_and_data(parsed, workspace=workspace, stdin=stdin, scan_sources=True)
        if parsed.command == "compile" and parsed.out is not None:  # type: ignore[attr-defined]
            artifacts = _artifact_bytes(bundle)
            publish_artifacts(parsed.out, workspace=workspace, artifacts=artifacts)  # type: ignore[attr-defined]
            data["out"] = output_relative(parsed.out, workspace=workspace)  # type: ignore[attr-defined]
            data["write_status"] = "published"
        if _raw_markdown_stdout(parsed):  # type: ignore[arg-type]
            stdout.write(bundle.canon_md)
            return 0
        message = "capsule preview" if parsed.command == "preview" else "capsule compiled"  # type: ignore[attr-defined]
        result = make_result(ok=True, command=parsed.command, failure_code="ok", message=message, data=data)  # type: ignore[attr-defined]
        return write_result(result, stdout=stdout, stderr=stderr, json_output=parsed.json_output, color=color)  # type: ignore[attr-defined]
    except (ArtifactError, CompileCliError, CapsuleBuildError) as exc:
        code = _failure_code(exc)
        message = _failure_message(code)
        result = make_result(ok=False, command=_command(parsed), failure_code=code, message=message)
        return write_result(result, stdout=stdout, stderr=stderr, json_output=_json_output(parsed), color=color)


def _bundle_and_data(parsed: object, *, workspace, stdin: TextIO | None, scan_sources: bool = False):
    sources = _load_sources(parsed, workspace=workspace, stdin=stdin)
    if scan_sources:
        _scan_loaded_sources(sources)
    records = _records_from_source(sources.records)
    atoms = _atoms_from_source(sources.atoms)
    descriptor = _descriptor(parsed.target)  # type: ignore[attr-defined]
    target = CapsuleTarget(descriptor.adapter_id, "CANON.md", descriptor.integration_tier, False)
    budget = _budget(parsed.profile, len(sources.records.data) + len(sources.atoms.data))  # type: ignore[attr-defined]
    source_state = SourceState(records_digest=source_state_sha256((sources.records.item(), sources.atoms.item())))
    request = CapsuleCompileRequest(
        profile=parsed.profile,  # type: ignore[attr-defined]
        target=target,
        source_state=source_state,
        budget=budget,
        atoms=atoms,
        records=records,
        receipts=(_source_receipt(sources),),
        does_not_prove=_does_not_prove(descriptor),
        required_atom_ids=_critical_atom_ids(atoms),
        readiness_probe_id=_probe_id(target, source_state, parsed.profile),  # type: ignore[attr-defined]
        readiness_target=_readiness_target(descriptor, target),
    )
    bundle = compile_capsule(request)
    return bundle, _result_data(bundle, parsed, sources)


def compile_bundle_for_cli(parsed: object, *, workspace, stdin: TextIO | None, scan_sources: bool = False):
    """Return the Task 7 compile bundle/result data without writing output."""
    return _bundle_and_data(parsed, workspace=workspace, stdin=stdin, scan_sources=scan_sources)


def _load_sources(parsed: object, *, workspace, stdin: TextIO | None) -> _LoadedSources:
    records_arg = parsed.records  # type: ignore[attr-defined]
    atoms_arg = parsed.atoms  # type: ignore[attr-defined]
    if records_arg == "-" and atoms_arg == "-":
        raise CompileCliError("invalid_args")
    records = _stdin_source(stdin, "records") if records_arg == "-" else read_source_file(records_arg, workspace=workspace)
    atoms = _stdin_source(stdin, "atoms") if atoms_arg == "-" else read_source_file(atoms_arg, workspace=workspace)
    return _LoadedSources(records, atoms)


def _stdin_source(stdin: TextIO | None, role: str) -> SourceBytes:
    if stdin is None:
        raise CompileCliError("invalid_args")
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            text = stdin.read(_STDIN_CHUNK_CHARS)
            if type(text) is not str:
                raise CompileCliError("invalid_args")
            if len(text) > _STDIN_CHUNK_CHARS:
                raise CompileCliError("invalid_args")
            if text == "":
                return SourceBytes(f"stdin-{role}", b"".join(chunks))
            data = text.encode("utf-8")
            total += len(data)
            if total > MAX_SOURCE_BYTES:
                raise CompileCliError("invalid_args")
            chunks.append(data)
    except CompileCliError:
        raise
    except (OSError, UnicodeEncodeError) as exc:
        raise CompileCliError("invalid_args") from exc


def _records_from_source(source: SourceBytes) -> tuple[Record, ...]:
    records: list[Record] = []
    for value in _jsonl_objects(source.data):
        try:
            record = Record.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise CompileCliError("invalid_args") from exc
        if validate_record(record):
            raise CompileCliError("invalid_args")
        records.append(record)
    return tuple(records)


def _atoms_from_source(source: SourceBytes) -> tuple[CanonAtom, ...]:
    atoms: list[CanonAtom] = []
    for value in _jsonl_objects(source.data):
        try:
            atom = CanonAtom.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise CompileCliError("invalid_args") from exc
        if validate_atom(atom):
            raise CompileCliError("invalid_args")
        atoms.append(atom)
    return tuple(atoms)


def _jsonl_objects(data: bytes) -> tuple[dict, ...]:
    try:
        return tuple(item.value for item in strict_jsonl_objects(data))
    except SourceParseError as exc:
        raise CompileCliError("invalid_args")


def _scan_loaded_sources(sources: _LoadedSources) -> None:
    for source in (sources.records, sources.atoms):
        try:
            text = utf8_text(source.data)
            findings = tuple(scan_text(source.path, source_id="source-path"))
            findings += tuple(scan_text(text, source_id="source-text"))
        except Exception as exc:
            raise CompileCliError("invalid_args") from exc
        if findings:
            raise CompileCliError("secret_quarantine")


def _descriptor(target_id: object):
    if type(target_id) is not str:
        raise CompileCliError("invalid_args")
    try:
        descriptor = descriptor_for(target_id)
    except KeyError as exc:
        raise CompileCliError("invalid_args") from exc
    if validate_adapter_descriptor(descriptor) or "CANON.md" not in descriptor.target_surfaces:
        raise CompileCliError("invalid_args")
    if descriptor.integration_tier == "unsupported":
        raise CompileCliError("unsupported_lifecycle")
    return descriptor


def _budget(profile: object, source_size: int) -> Budget:
    if type(profile) is not str or profile not in _BUDGETS:
        raise CompileCliError("invalid_args")
    estimated = min(_BUDGETS[profile], (source_size + 3) // 4)
    return Budget(profile, _BUDGETS[profile], estimated, "known")


def _critical_atom_ids(atoms: tuple[CanonAtom, ...]) -> tuple[str, ...]:
    return tuple(atom.id for atom in atoms if atom.critical is True)


def _source_receipt(sources: _LoadedSources) -> dict[str, object]:
    return {
        "atoms_path": sources.atoms.path,
        "atoms_sha256": sha256_bytes(sources.atoms.data),
        "kind": "cli-compile-source-state",
        "records_path": sources.records.path,
        "records_sha256": sha256_bytes(sources.records.data),
    }


def _does_not_prove(descriptor: object) -> tuple[str, ...]:
    return tuple(descriptor.known_unknowns) + (  # type: ignore[attr-defined]
        "This compile does not prove readiness acknowledgement or host-level enforcement.",
    )


def _probe_id(target: CapsuleTarget, source_state: SourceState, profile: str) -> str:
    payload = {"profile": profile, "source_state": source_state.to_dict(), "target": target.to_dict()}
    return "probe-" + sha256_text(canonical_json_text(payload)).removeprefix("sha256:")[:16]


def _readiness_target(descriptor: object, target: CapsuleTarget) -> dict[str, object]:
    return {
        "adapter": target.adapter,
        "bootstrap": descriptor.bootstrap,  # type: ignore[attr-defined]
        "host_enforcement_observed": target.host_enforcement_observed,
        "integration_tier": target.integration_tier,
        "known_unknowns": list(descriptor.known_unknowns),  # type: ignore[attr-defined]
        "surface": target.surface,
    }


def _result_data(bundle: object, parsed: object, sources: _LoadedSources) -> dict[str, object]:
    return {
        "artifacts": list(ARTIFACT_NAMES),
        "capsule_id": bundle.capsule.capsule_id,  # type: ignore[attr-defined]
        "canon_md_sha256": sha256_text(bundle.canon_md),  # type: ignore[attr-defined]
        "manifest_sha256": sha256_bytes(bundle.manifest_bytes),  # type: ignore[attr-defined]
        "mode": parsed.command,  # type: ignore[attr-defined]
        "offline": parsed.offline,  # type: ignore[attr-defined]
        "out": None,
        "profile": parsed.profile,  # type: ignore[attr-defined]
        "readiness_probe": bundle.readiness_probe.to_dict(),  # type: ignore[attr-defined]
        "source_inputs": [sources.records.path, sources.atoms.path],
        "source_state": bundle.capsule.source_state.to_dict(),  # type: ignore[attr-defined]
        "target": bundle.capsule.target.to_dict(),  # type: ignore[attr-defined]
        "write_status": "none",
    }


def _artifact_bytes(bundle: object) -> dict[str, bytes]:
    return {
        "canon.capsule.json": bundle.manifest_bytes,  # type: ignore[attr-defined]
        "CANON.md": bundle.canon_md.encode("utf-8"),  # type: ignore[attr-defined]
        "readiness-probe.json": canonical_json_text(bundle.readiness_probe.to_dict()).encode("utf-8"),  # type: ignore[attr-defined]
    }


def bundle_artifacts(bundle: object) -> dict[str, bytes]:
    """Return Task 7 artifact bytes for callers that need publish semantics."""
    return _artifact_bytes(bundle)


def _raw_markdown_stdout(parsed: object) -> bool:
    return parsed.command == "compile" and parsed.out is None and parsed.json_output is False  # type: ignore[attr-defined]


def _failure_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if type(code) is str:
        return code
    text = str(exc)
    return "critical_atom_loss" if "required atom" in text else "invalid_args"


def _failure_message(code: str) -> str:
    return {
        "conflict": "compile output conflict",
        "critical_atom_loss": "critical atom loss",
        "io_error": "compile I/O failed",
        "source_unreachable": "compile source unreachable",
        "unsafe_path": "unsafe compile path",
        "unsupported_lifecycle": "unsupported compile target",
    }.get(code, "invalid compile input")


def _command(parsed: object) -> str:
    command = getattr(parsed, "command", "compile")
    return command if type(command) is str and command else "compile"


def _json_output(parsed: object) -> bool:
    return getattr(parsed, "json_output", False) is True


__all__ = ["bundle_artifacts", "compile_bundle_for_cli", "run_compile_command"]
