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
from .gateway_operation_validation import TERMINAL_EVENTS
from .gateway_run_outcome import derive_run_outcome, validate_run_outcome


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


_DERIVED = ("effect_evidence", "run_outcome")


def _without_effect(value: dict) -> dict:
    projected = dict(value)
    for key in _DERIVED:
        projected.pop(key, None)
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
    # Both derived blocks attach together or not at all: a projection either
    # carries everything the accepted trace prefix yields, or stays legacy.
    # The run outcome reports a bad budget record as unverifiable rather than
    # raising, so the fallback below is reached only when the trace itself
    # cannot be read or the effect block cannot be derived.
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
        candidate["run_outcome"] = derive_run_outcome(
            records, terminal_state=terminal_state)
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
    if not _is_agent_projection(result):
        return
    terminal, basis = _terminal_and_basis(history)
    state = terminal["event_type"].removeprefix("operation_")
    _validate_projection_binding(result, operation_ref, journey_ref, state)
    if not any(key in result for key in _DERIVED):
        return
    trace, records = _read_matching_records(
        state_root, owner_ref, journey_ref, operation_ref, result)
    if "effect_evidence" in result:
        validate_effect_evidence(
            records,
            trace_ref=trace.ref,
            terminal_state=state,
            terminal_basis_event_type=basis["event_type"],
            terminal_basis_event_sha256=basis["event_sha256"],
            submitted=result["effect_evidence"],
        )
    if "run_outcome" in result:
        validate_run_outcome(records, terminal_state=state,
                             submitted=result["run_outcome"])
    expected_hash = canonical_sha256(
        {key: value for key, value in result.items()
         if key != "projection_sha256"})
    if result.get("projection_sha256") != expected_hash:
        raise ValueError("invalid effect projection hash")
