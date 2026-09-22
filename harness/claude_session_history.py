"""Owned Claude session-history provenance checks."""
from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from .evidence_json import canonical_sha256, strict_load_json_value
from .journey_types import SHA256_PATTERN
from .provider_session_contract import ProviderSessionError


@dataclass(frozen=True)
class ClaudeHistoryObservation:
    status: str
    provider_session: dict
    last_provider_event_id: str = ""
    input_sha256: str = ""
    terminal_result_sha256: str = ""
    history_store_head_sha256: str = ""
    detail_code: str = ""


def load_owned_history(pointer: dict, *, state_root: Path) -> list[dict]:
    if type(pointer) is not dict or pointer.get("type") != "jsonl":
        raise _error("AGENT_BINDING_DRIFT", "invalid_history_pointer")
    path = _contained_path(str(pointer.get("path") or ""), Path(state_root))
    if not path.is_file():
        raise _error("AGENT_NATIVE_INCOMPLETE", "missing_history")
    raw = path.read_bytes()
    _check_pointer_sha(pointer, raw)
    records = []
    try:
        for line in raw.splitlines():
            if not line.strip():
                continue
            value = strict_load_json_value(line)
            if type(value) is not dict or type(value.get("type")) is not str:
                raise ValueError("history entry must be an object with type")
            records.append(value)
    except ProviderSessionError:
        raise
    except Exception as exc:
        raise _error("AGENT_NATIVE_INCOMPLETE", "malformed_history") from exc
    return records


def load_owned_terminal_observation(pointer: dict, *, state_root: Path) -> dict:
    if type(pointer) is not dict or pointer.get("type") != "json":
        raise _error("AGENT_BINDING_DRIFT", "invalid_terminal_pointer")
    path = _contained_path(str(pointer.get("path") or ""), Path(state_root))
    if not path.is_file():
        raise _error("AGENT_NATIVE_INCOMPLETE", "missing_terminal_observation")
    try:
        raw = path.read_bytes()
        _check_pointer_sha(pointer, raw)
        value = strict_load_json_value(raw)
    except ProviderSessionError:
        raise
    except Exception as exc:
        raise _error("AGENT_NATIVE_INCOMPLETE", "malformed_terminal_observation") from exc
    if type(value) is not dict:
        raise _error("AGENT_NATIVE_INCOMPLETE", "malformed_terminal_observation")
    return value


def observe_source_history(records: list[dict], source: dict,
                           terminal_observation: dict | None = None
                           ) -> ClaudeHistoryObservation:
    session = dict(source.get("provider_session") or {})
    if not records:
        return _observation("missing", session, "missing_history")
    if not _records_valid(records):
        return _observation("indeterminate", session, "malformed_history")
    if _has_mirror_error(records):
        return _observation("indeterminate", session, "mirror_error")
    if terminal_observation is None:
        return _observation("indeterminate", session, "missing_terminal_observation")
    if terminal_observation.get("provider") != "claude":
        return _observation("indeterminate", session, "provider_mismatch")
    expected_session = session.get("native_session_id") or ""
    if terminal_observation.get("native_session_id") != expected_session:
        return _observation("indeterminate", session, "native_session_mismatch")
    if terminal_observation.get("source_operation_ref") != source.get("operation_ref"):
        return _observation("indeterminate", session, "source_operation_mismatch")
    expected_input = source.get("input_sha256")
    if not expected_input:
        return _observation("indeterminate", session, "missing_source_input_sha256")
    if terminal_observation.get("input_sha256") != expected_input:
        return _observation("indeterminate", session, "input_mismatch")
    for source_key, terminal_key, detail in (
        ("result_sha256", "source_result_sha256", "source_result_mismatch"),
        ("terminal_event_sha256", "source_terminal_event_sha256",
         "source_terminal_event_mismatch"),
        ("trace_head_sha256", "source_trace_head_sha256", "source_trace_head_mismatch"),
    ):
        expected = source.get(source_key)
        if expected and terminal_observation.get(terminal_key) != expected:
            return _observation("indeterminate", session, detail)
    expected_receipt = source.get("input_receipt_sha256")
    if (expected_receipt and terminal_observation.get(
            "source_input_receipt_sha256") != expected_receipt):
        return _observation("indeterminate", session, "source_input_receipt_mismatch")
    store_head = canonical_sha256(records)
    if terminal_observation.get("history_store_head_sha256") != store_head:
        return _observation("indeterminate", session, "history_store_head_mismatch")
    event_id = terminal_observation.get("last_provider_event_id")
    terminal_hash = terminal_observation.get("terminal_result_sha256")
    input_hash = terminal_observation.get("input_sha256")
    if not all(isinstance(value, str) and value for value in (
            event_id, terminal_hash, input_hash)):
        return _observation("indeterminate", session, "terminal_observation_incomplete")
    return ClaudeHistoryObservation(
        "native_terminal_observed", session, event_id, input_hash,
        terminal_hash, store_head, "terminal_observation_bound")


def _records_valid(records: list[dict]) -> bool:
    return all(type(record) is dict and type(record.get("type")) is str
               for record in records)


def _has_mirror_error(records: list[dict]) -> bool:
    for record in records:
        if record.get("type") == "mirror_error":
            return True
        if record.get("type") == "system" and record.get("subtype") == "mirror_error":
            return True
    return False


def _observation(status: str, session: dict, detail: str) -> ClaudeHistoryObservation:
    return ClaudeHistoryObservation(status, dict(session), detail_code=detail)


def _contained_path(value: str, state_root: Path) -> Path:
    if not value:
        raise _error("AGENT_BINDING_DRIFT", "empty_history_path")
    windows = PureWindowsPath(value)
    if Path(value).is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise _error("AGENT_BINDING_DRIFT", "unsafe_history_path")
    if ".." in windows.parts or ".." in Path(value).parts:
        raise _error("AGENT_BINDING_DRIFT", "unsafe_history_path")
    root = state_root.resolve()
    candidate = (root / value).resolve()
    try:
        if os.path.commonpath((os.path.normcase(str(root)),
                               os.path.normcase(str(candidate)))) != os.path.normcase(str(root)):
            raise ValueError
    except ValueError as exc:
        raise _error("AGENT_BINDING_DRIFT", "unsafe_history_path") from exc
    return candidate


def _check_pointer_sha(pointer: dict, raw: bytes) -> None:
    expected = pointer.get("sha256")
    if expected is None:
        raise _error("AGENT_BINDING_DRIFT", "missing_owned_pointer_sha256")
    if type(expected) is not str or SHA256_PATTERN.fullmatch(expected) is None:
        raise _error("AGENT_BINDING_DRIFT", "invalid_owned_pointer_sha256")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise _error("AGENT_BINDING_DRIFT", "owned_pointer_sha256_mismatch")


def _error(code: str, detail_code: str) -> ProviderSessionError:
    return ProviderSessionError(
        code, history_status="indeterminate",
        side_effect_status="indeterminate", detail_code=detail_code)
