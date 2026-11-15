from __future__ import annotations

import json
from dataclasses import dataclass

from .atom import CanonAtom, validate_atom
from .bootstrap_runtime_error import BootstrapRuntimeError
from .bootstrap_validation import thaw_mapping_or_none
from .bootstrap_sources import SourceParseError, strict_jsonl_objects, utf8_text
from .canonical_json import CanonicalJSONError, canonical_json_text
from .capsule import Budget, SourceState
from .cli_artifacts import ArtifactError, SourceBytes, WorkspaceRoot, read_source_file
from .schema import Record
from .secret_quarantine import SecretQuarantineError, scan_text
from .source_state import SourceStateItem, source_state_sha256
from .validator import validate_record

_BUDGETS = {"needle": 2048, "handoff": 8192, "archive": 32768, "custom": 8192}


@dataclass(frozen=True, slots=True)
class BootstrapInputs:
    source_state: SourceState
    source_items: tuple[SourceStateItem, ...]
    source_inputs: tuple[SourceBytes, ...]
    records: tuple[Record, ...]
    atoms: tuple[CanonAtom, ...]
    budget: Budget
    budget_key: str
    readiness_response: dict[str, object] | None


def load_bootstrap_inputs(snapshot: dict[str, object], workspace: WorkspaceRoot) -> BootstrapInputs:
    sources = _load_source_pair(snapshot, workspace)
    records, atoms = _parse_sources(sources)
    source_items = tuple(source.item() for source in sources)
    source_state = SourceState(records_digest=source_state_sha256(source_items))
    budget = _budget(snapshot["profile"], sum(len(source.data) for source in sources))
    response = _readiness_response(snapshot, workspace)
    return BootstrapInputs(source_state, source_items, sources, records, atoms, budget,
                           canonical_json_text(budget.to_dict()).removesuffix("\n"), response)


def source_item_dict(item: SourceStateItem) -> dict[str, object]:
    return {"path": item.path, "sha256": item.sha256, "size": item.size}


def _load_source_pair(snapshot: dict[str, object], workspace: WorkspaceRoot) -> tuple[SourceBytes, ...]:
    records_path, atoms_path = snapshot["records_path"], snapshot["atoms_path"]
    if records_path is None and atoms_path is None: return ()
    if records_path is None or atoms_path is None or records_path == "-" or atoms_path == "-":
        raise BootstrapRuntimeError("invalid_args", "invalid bootstrap source arguments")
    return (_read_source(records_path, workspace), _read_source(atoms_path, workspace))


def _read_source(raw: object, workspace: WorkspaceRoot) -> SourceBytes:
    try:
        source = read_source_file(raw, workspace=workspace); _vetted_text(source); return source
    except ArtifactError as exc:
        raise BootstrapRuntimeError(exc.code, "bootstrap source read failed") from exc


def _parse_sources(sources: tuple[SourceBytes, ...]) -> tuple[tuple[Record, ...], tuple[CanonAtom, ...]]:
    return ((), ()) if not sources else (_records_from_source(sources[0]), _atoms_from_source(sources[1]))


def _records_from_source(source: SourceBytes) -> tuple[Record, ...]:
    records: list[Record] = []
    for value in _jsonl_objects(source):
        try: record = Record.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise BootstrapRuntimeError("invalid_args", "invalid bootstrap record source") from exc
        if validate_record(record): raise BootstrapRuntimeError("invalid_args", "invalid bootstrap record source")
        records.append(record)
    return tuple(records)


def _atoms_from_source(source: SourceBytes) -> tuple[CanonAtom, ...]:
    atoms: list[CanonAtom] = []
    for value in _jsonl_objects(source):
        try: atom = CanonAtom.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise BootstrapRuntimeError("invalid_args", "invalid bootstrap atom source") from exc
        if validate_atom(atom): raise BootstrapRuntimeError("invalid_args", "invalid bootstrap atom source")
        atoms.append(atom)
    return tuple(atoms)


def _jsonl_objects(source: SourceBytes) -> tuple[dict, ...]:
    try: return tuple(item.value for item in strict_jsonl_objects(source.data))
    except SourceParseError as exc:
        raise BootstrapRuntimeError(exc.code, "invalid bootstrap source") from exc


def _readiness_response(snapshot: dict[str, object], workspace: WorkspaceRoot) -> dict[str, object] | None:
    direct, path = snapshot["readiness_response"], snapshot["readiness_response_path"]
    if path is not None:
        if path == "-": raise BootstrapRuntimeError("invalid_args", "invalid readiness response path")
        return _json_object(_read_source(path, workspace))
    try:
        response = thaw_mapping_or_none(direct)  # type: ignore[arg-type]
        if response is not None: _scan_readiness_response(response)
        return response
    except TypeError as exc:
        raise BootstrapRuntimeError("invalid_args", "invalid readiness response") from exc


def _json_object(source: SourceBytes) -> dict[str, object]:
    text = _vetted_text(source)
    try: value = json.loads(text, object_pairs_hook=_object_no_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        raise BootstrapRuntimeError("invalid_args", "invalid readiness response") from exc
    if type(value) is not dict: raise BootstrapRuntimeError("invalid_args", "invalid readiness response")
    _scan_readiness_response(value)
    return value


def _scan_readiness_response(response: dict[str, object]) -> None:
    try: rendered = canonical_json_text(response)
    except (CanonicalJSONError, TypeError, ValueError) as exc:
        raise BootstrapRuntimeError("invalid_args", "invalid readiness response") from exc
    _scan_or_fail(rendered)
    for value in _string_leaves(response):
        _scan_or_fail(value)


def _scan_or_fail(text: str) -> None:
    try:
        findings = scan_text(text, source_id="readiness-response")
    except SecretQuarantineError as exc:
        raise BootstrapRuntimeError("invalid_args", "invalid readiness response") from exc
    if findings:
        raise BootstrapRuntimeError("secret_quarantine", "secret quarantine")


def _string_leaves(value: object):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for item in value.values():
            yield from _string_leaves(item)
    elif type(value) is list:
        for item in value:
            yield from _string_leaves(item)


def _vetted_text(source: SourceBytes) -> str:
    try:
        text = utf8_text(source.data)
        if scan_text(text, source_id=source.path): raise BootstrapRuntimeError("secret_quarantine", "secret quarantine")
        return text
    except BootstrapRuntimeError: raise
    except Exception as exc:
        raise BootstrapRuntimeError("invalid_args", "invalid bootstrap source text") from exc


def _object_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result: raise ValueError("duplicate object key")
        result[key] = value
    return result


def _budget(profile: object, source_size: int) -> Budget:
    if type(profile) is not str or profile not in _BUDGETS:
        raise BootstrapRuntimeError("invalid_args", "invalid bootstrap profile")
    return Budget(profile, _BUDGETS[profile], min(_BUDGETS[profile], (source_size + 3) // 4), "known")


__all__ = ["BootstrapInputs", "load_bootstrap_inputs", "source_item_dict"]
