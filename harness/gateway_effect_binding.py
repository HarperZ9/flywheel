"""Bind terminal projections to recomputed private-trace effect evidence."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_sha256
from .gateway_agent_projection import SCHEMA as AGENT_PROJECTION_SCHEMA
from .gateway_agent_trace import AgentTrace, TraceError
from .gateway_effect_evidence import (
    derive_effect_evidence,
    validate_effect_evidence,
)
from .gateway_operation_recovery import TERMINAL_EVENTS


def _is_agent_projection(value: object) -> bool:
    return type(value) is dict and value.get("schema") == AGENT_PROJECTION_SCHEMA


def _rehash_projection(value: dict) -> dict:
    projected = dict(value)
    projected.pop("projection_sha256", None)
    projected["projection_sha256"] = canonical_sha256(projected)
    return projected


def _validate_projection_binding(value: dict, operation_ref: str,
                                 journey_ref: str,
                                 terminal_state: str) -> None:
    if (not _is_agent_projection(value)
            or value.get("operation_ref") != operation_ref
            or value.get("journey_ref") != journey_ref
            or value.get("state") != terminal_state):
        raise ValueError("invalid terminal projection binding")
    digest = value.get("projection_sha256")
    expected = canonical_sha256(
        {key: item for key, item in value.items()
         if key != "projection_sha256"})
    if type(digest) is not str or digest != expected:
        raise ValueError("invalid terminal projection binding")


def _without_effect(value: dict) -> dict:
    projected = dict(value)
    projected.pop("effect_evidence", None)
    return projected


def _read_matching_records(state_root: Path, owner_ref: str, journey_ref: str,
                           operation_ref: str, projection: dict):
    trace = AgentTrace(state_root, owner_ref, journey_ref, operation_ref)
    records = trace.read_reference(projection.get("trace_ref"))
    if (projection.get("record_count") != len(records)
            or projection.get("trace_head_sha256") != trace.head):
        raise TraceError()
    return trace, records


def attach_terminal_effect_evidence(state_root: Path, owner_ref: str,
                                    journey_ref: str, operation_ref: str,
                                    result: dict, terminal_state: str,
                                    basis_event: dict) -> dict:
    if not _is_agent_projection(result):
        return result
    clean = _without_effect(result)
    _validate_projection_binding(clean, operation_ref, journey_ref,
                                 terminal_state)
    try:
        trace, records = _read_matching_records(
            state_root, owner_ref, journey_ref, operation_ref, clean)
        candidate = dict(clean)
        candidate.pop("projection_sha256", None)
        candidate["effect_evidence"] = derive_effect_evidence(
            records,
            trace_ref=trace.ref,
            terminal_state=terminal_state,
            terminal_basis_event_type=basis_event["event_type"],
            terminal_basis_event_sha256=basis_event["event_sha256"],
        )
        candidate["projection_sha256"] = canonical_sha256(candidate)
        return candidate
    except Exception:
        pass
    return clean


def _terminal_and_basis(history: list[dict]) -> tuple[dict, dict]:
    terminal = next((event for event in history
                     if event["event_type"] in TERMINAL_EVENTS), None)
    if terminal is None:
        raise ValueError("missing terminal event")
    basis = next((event for event in history
                  if event["event_sha256"] == terminal["payload"]["basis_event_sha256"]), None)
    if basis is None:
        raise ValueError("missing terminal basis")
    return terminal, basis


def validate_terminal_effect_evidence(state_root: Path, owner_ref: str,
                                      journey_ref: str, operation_ref: str,
                                      result: dict, history: list[dict]) -> None:
    if not _is_agent_projection(result) or "effect_evidence" not in result:
        if _is_agent_projection(result):
            terminal, _ = _terminal_and_basis(history)
            _validate_projection_binding(
                result, operation_ref, journey_ref,
                terminal["event_type"].removeprefix("operation_"))
        return
    terminal, basis = _terminal_and_basis(history)
    _validate_projection_binding(
        result, operation_ref, journey_ref,
        terminal["event_type"].removeprefix("operation_"))
    trace, records = _read_matching_records(
        state_root, owner_ref, journey_ref, operation_ref, result)
    validate_effect_evidence(
        records,
        trace_ref=trace.ref,
        terminal_state=terminal["event_type"].removeprefix("operation_"),
        terminal_basis_event_type=basis["event_type"],
        terminal_basis_event_sha256=basis["event_sha256"],
        submitted=result["effect_evidence"],
    )
    expected_hash = canonical_sha256(
        {key: value for key, value in result.items()
         if key != "projection_sha256"})
    if result.get("projection_sha256") != expected_hash:
        raise ValueError("invalid effect projection hash")
