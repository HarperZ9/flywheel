from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TextIO

from .atom import CanonAtom, validate_atom
from .bootstrap_sources import SourceParseError, strict_jsonl_objects, utf8_text
from .canonical_json import canonical_json_text, sha256_bytes
from .capsule import Budget, CapsuleBuildError, SourceState, compile_capsule
from .cli_artifacts import MAX_SOURCE_BYTES, ArtifactError, SourceBytes, WorkspaceRoot, checked_workspace, read_source_file
from .cli_format import make_result, write_result
from .rescue import RescueError, build_rescue_request
from .rescue_artifacts import build_artifact_bytes, result_data, transcript_metadata
from .rescue_output import RescueOutputError, publish_rescue_artifacts
from .schema import Record
from .secret_quarantine import scan_text
from .source_state import source_state_sha256
from .validator import validate_record

_BUDGETS = {"needle": 2048, "handoff": 8192, "archive": 32768, "custom": 8192}
_STDIN_CHUNK_CHARS = 65536


class RescueCliError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _LoadedSources:
    records: SourceBytes
    atoms: SourceBytes
    transcript: SourceBytes | None


@dataclass(frozen=True, slots=True)
class _PreparedRescue:
    workspace: WorkspaceRoot
    artifacts: dict[str, bytes]
    data: dict[str, object]
    source_labels: tuple[str, str]


def run_rescue_command(
    parsed: object,
    *,
    stdin: TextIO | None,
    stdout: TextIO,
    stderr: TextIO,
    color: bool,
) -> int:
    try:
        prepared = _prepare_rescue(
            workspace_arg=parsed.workspace, records_arg=parsed.records, atoms_arg=parsed.atoms,  # type: ignore[attr-defined]
            target_arg=parsed.target, profile_arg=parsed.profile, offline_arg=parsed.offline,  # type: ignore[attr-defined]
            stdin=stdin, transcript_arg=parsed.include_transcript,  # type: ignore[attr-defined]
        )
        data = dict(prepared.data)
        if parsed.out is not None:  # type: ignore[attr-defined]
            out, status = publish_rescue_artifacts(
                parsed.out, workspace=prepared.workspace, artifacts=prepared.artifacts,  # type: ignore[attr-defined]
                reserved_labels=prepared.source_labels,
            )
            data["out"] = out
            data["write_status"] = "idempotent" if status == "idempotent" else "published"
        _scan_public_json(data, "rescue-result")
        result = make_result(ok=True, command="rescue", failure_code="ok", message="rescue bundle ready", data=data)
        return write_result(result, stdout=stdout, stderr=stderr, json_output=_json_output(parsed), color=color)
    except (ArtifactError, CapsuleBuildError, RescueCliError, RescueError, RescueOutputError) as exc:
        code = _failure_code(exc)
        result = make_result(ok=False, command="rescue", failure_code=code, message=_failure_message(code))
        return write_result(result, stdout=stdout, stderr=stderr, json_output=_json_output(parsed), color=color)


def build_rescue_artifacts(
    *,
    workspace: str,
    records_path: str,
    atoms_path: str,
    target: str,
    profile: str,
    offline: bool,
    stdin: TextIO | None,
    transcript_path: str | None,
) -> tuple[dict[str, bytes], dict[str, object]]:
    prepared = _prepare_rescue(
        workspace_arg=workspace, records_arg=records_path, atoms_arg=atoms_path,
        target_arg=target, profile_arg=profile, offline_arg=offline,
        stdin=stdin, transcript_arg=transcript_path,
    )
    return dict(prepared.artifacts), dict(prepared.data)


def _prepare_rescue(
    *,
    workspace_arg: object,
    records_arg: object,
    atoms_arg: object,
    target_arg: object,
    profile_arg: object,
    offline_arg: object,
    stdin: TextIO | None,
    transcript_arg: object,
) -> _PreparedRescue:
    if type(offline_arg) is not bool:
        raise RescueCliError("invalid_args")
    workspace = checked_workspace(workspace_arg)
    sources = _load_sources(records_arg, atoms_arg, transcript_arg, workspace=workspace, stdin=stdin)
    _scan_loaded_sources(sources)
    records = _records_from_source(sources.records)
    atoms = _atoms_from_source(sources.atoms)
    source_state = SourceState(records_digest=source_state_sha256((sources.records.item(), sources.atoms.item())))
    request = build_rescue_request(
        records=records, atoms=atoms, target=_text(target_arg), source_state=source_state,
        budget=_budget(profile_arg, len(sources.records.data) + len(sources.atoms.data)), profile=_text(profile_arg),
    )
    request = replace(request, receipts=(_source_receipt(sources),))
    bundle = compile_capsule(request)
    transcript = transcript_metadata(sources.transcript)
    artifacts = build_artifact_bytes(bundle, request, transcript, offline_arg)
    data = result_data(bundle, request, sources.records, sources.atoms, transcript, offline_arg)
    _scan_outputs(data, artifacts)
    return _PreparedRescue(workspace, artifacts, data, (sources.records.path, sources.atoms.path))


def _load_sources(
    records_arg: object,
    atoms_arg: object,
    transcript_arg: object,
    *,
    workspace: WorkspaceRoot,
    stdin: TextIO | None,
) -> _LoadedSources:
    if sum(1 for value in (records_arg, atoms_arg, transcript_arg) if value == "-") > 1:
        raise RescueCliError("invalid_args")
    records = _stdin_source(stdin, "records") if records_arg == "-" else read_source_file(records_arg, workspace=workspace)
    atoms = _stdin_source(stdin, "atoms") if atoms_arg == "-" else read_source_file(atoms_arg, workspace=workspace)
    transcript = _load_transcript(transcript_arg, workspace=workspace, stdin=stdin)
    return _LoadedSources(records, atoms, transcript)


def _load_transcript(raw: object, *, workspace: WorkspaceRoot, stdin: TextIO | None) -> SourceBytes | None:
    if raw is None:
        return None
    if raw == "-":
        return _stdin_source(stdin, "transcript")
    return read_source_file(raw, workspace=workspace)


def _stdin_source(stdin: TextIO | None, role: str) -> SourceBytes:
    if stdin is None:
        raise RescueCliError("invalid_args")
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            text = stdin.read(_STDIN_CHUNK_CHARS)
            if type(text) is not str or len(text) > _STDIN_CHUNK_CHARS:
                raise RescueCliError("invalid_args")
            if text == "":
                return SourceBytes(f"stdin-{role}", b"".join(chunks))
            data = text.encode("utf-8")
            total += len(data)
            if total > MAX_SOURCE_BYTES:
                raise RescueCliError("invalid_args")
            chunks.append(data)
    except RescueCliError:
        raise
    except (OSError, UnicodeEncodeError) as exc:
        raise RescueCliError("invalid_args") from exc


def _scan_loaded_sources(sources: _LoadedSources) -> None:
    for role, source in (("records", sources.records), ("atoms", sources.atoms)):
        _scan_source(source, role)
    if sources.transcript is not None:
        _scan_source(sources.transcript, "transcript")


def _scan_source(source: SourceBytes, role: str) -> str:
    try:
        text = utf8_text(source.data)
        findings = tuple(scan_text(source.path, source_id=f"{role}-path"))
        findings += tuple(scan_text(text, source_id=f"{role}-text"))
    except Exception as exc:
        raise RescueCliError("invalid_args") from exc
    if findings:
        raise RescueCliError("secret_quarantine")
    return text


def _records_from_source(source: SourceBytes) -> tuple[Record, ...]:
    records: list[Record] = []
    for value in _jsonl_objects(source.data):
        try:
            record = Record.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise RescueCliError("invalid_args") from exc
        if validate_record(record):
            raise RescueCliError("invalid_args")
        records.append(record)
    return tuple(records)


def _atoms_from_source(source: SourceBytes) -> tuple[CanonAtom, ...]:
    atoms: list[CanonAtom] = []
    for value in _jsonl_objects(source.data):
        try:
            atom = CanonAtom.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise RescueCliError("invalid_args") from exc
        if validate_atom(atom):
            raise RescueCliError("invalid_args")
        atoms.append(atom)
    return tuple(atoms)


def _jsonl_objects(data: bytes) -> tuple[dict, ...]:
    try:
        return tuple(item.value for item in strict_jsonl_objects(data))
    except SourceParseError as exc:
        raise RescueCliError("invalid_args") from exc


def _source_receipt(sources: _LoadedSources) -> dict[str, object]:
    return {
        "atoms_path": sources.atoms.path,
        "atoms_sha256": sha256_bytes(sources.atoms.data),
        "kind": "cli-compile-source-state",
        "records_path": sources.records.path,
        "records_sha256": sha256_bytes(sources.records.data),
    }


def _budget(profile: object, source_size: int) -> Budget:
    if type(profile) is not str or profile not in _BUDGETS:
        raise RescueCliError("invalid_args")
    estimated = min(_BUDGETS[profile], (source_size + 3) // 4)
    return Budget(profile, _BUDGETS[profile], estimated, "known")


def _text(value: object) -> str:
    if type(value) is not str:
        raise RescueCliError("invalid_args")
    return value


def _scan_outputs(data: dict[str, object], artifacts: dict[str, bytes]) -> None:
    _scan_public_json(data, "rescue-result")
    for name, raw in artifacts.items():
        _scan_text_bytes(raw, f"rescue-artifact-{name}")


def _scan_public_json(value: object, source_id: str) -> None:
    _scan_text(canonical_json_text(value), source_id)


def _scan_text_bytes(raw: bytes, source_id: str) -> None:
    try:
        text = utf8_text(raw)
    except SourceParseError as exc:
        raise RescueCliError("invalid_args") from exc
    _scan_text(text, source_id)


def _scan_text(text: str, source_id: str) -> None:
    try:
        findings = tuple(scan_text(text, source_id=source_id))
    except Exception as exc:
        raise RescueCliError("invalid_args") from exc
    if findings:
        raise RescueCliError("secret_quarantine")


def _failure_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return code if type(code) is str else "invalid_args"


def _failure_message(code: str) -> str:
    return {
        "conflict": "rescue output conflict",
        "critical_atom_loss": "critical atom loss",
        "io_error": "rescue I/O failed",
        "secret_quarantine": "rescue source quarantined",
        "source_unreachable": "rescue source unreachable",
        "unsafe_path": "unsafe rescue path",
        "unsupported_lifecycle": "unsupported rescue target",
    }.get(code, "invalid rescue input")


def _json_output(parsed: object) -> bool:
    return getattr(parsed, "json_output", False) is True


__all__ = ["RescueCliError", "build_rescue_artifacts", "run_rescue_command"]
