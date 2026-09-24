"""Read provider-native recovery state from existing operation artifacts."""
from __future__ import annotations

from pathlib import Path

from .gateway_agent_trace import AgentTrace

_NATIVE_KEYS = (
    "provider", "native_session_id", "native_thread_id", "native_turn_id",
    "last_provider_event_id", "config_digest", "capability_digest",
)


def read_provider_trace(state_root: Path | str, owner_ref: str, journey_ref: str,
                        operation_ref: str) -> dict:
    trace = AgentTrace(Path(state_root), owner_ref, journey_ref, operation_ref)
    records = trace.read()
    return {
        "trace_ref": trace.ref,
        "record_count": len(records),
        "trace_head_sha256": trace.head,
        "records": records,
    }


def latest_provider_session_from_trace(records: list[dict]) -> dict | None:
    latest = None
    for record in records:
        payload = record.get("payload", {})
        candidate = payload.get("provider_session")
        if type(candidate) is dict:
            latest = _session(candidate)
            continue
        if type(payload) is dict and payload.get("phase") in {
                "native_binding", "input_sent", "provider_result"}:
            folded = _session(payload)
            if folded:
                latest = folded
    return latest


def provider_session_from_result(result: object) -> dict | None:
    if type(result) is not dict:
        return None
    return _session(result.get("provider_session"))


def _session(value: object) -> dict | None:
    if type(value) is not dict:
        return None
    result = {key: value.get(key, "") for key in _NATIVE_KEYS
              if type(value.get(key, "")) is str}
    return result if result.get("provider") else None
