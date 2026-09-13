"""Content-free effect observations derived from accepted private traces."""
from __future__ import annotations

import re

from .evidence_json import canonical_bytes, canonical_sha256
from .gateway_agent_trace import GENESIS

SCHEMA = "flywheel.gateway-effect-evidence/v1"
MAX_VISIBLE_OBSERVATIONS = 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TRACE = re.compile(r"agt_[0-9a-f]{32}\Z")
_TERMINAL_STATES = {"completed", "failed", "cancelled"}
_BASIS_EVENTS = {"operation_queued", "operation_started", "cancel_requested"}
_UNKNOWN_SCOPE = [
    "NOT_ROLLBACK",
    "NOT_EFFECT_ABSENCE",
    "NOT_CURRENT_FILESYSTEM_STATE",
    "UNRECORDED_ACTIONS_NOT_EXCLUDED",
    "TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN",
    "EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN",
]
_DOES_NOT_PROVE = [
    "semantic correctness",
    "complete workstation observation",
    "current filesystem state",
    "absence of effects outside the accepted trace prefix",
    "rollback or remote cancellation",
]


class EffectEvidenceError(ValueError):
    def __init__(self):
        super().__init__("GATEWAY_EFFECT_EVIDENCE_INVALID")


def _sha(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _validate_inputs(records: list[dict], trace_ref: str, terminal_state: str,
                     terminal_basis_event_type: str,
                     terminal_basis_event_sha256: str) -> None:
    if (type(records) is not list
            or type(trace_ref) is not str or _TRACE.fullmatch(trace_ref) is None
            or terminal_state not in _TERMINAL_STATES
            or terminal_basis_event_type not in _BASIS_EVENTS
            or not _sha(terminal_basis_event_sha256)):
        raise EffectEvidenceError()
    for index, record in enumerate(records):
        if (type(record) is not dict
                or type(record.get("sequence")) is not int
                or record.get("sequence") != index
                or not _sha(record.get("record_sha256"))
                or type(record.get("payload")) is not dict
                or type(record.get("kind")) is not str):
            raise EffectEvidenceError()
    canonical_bytes(records)


def _trace_head(records: list[dict]) -> str:
    return records[-1]["record_sha256"] if records else GENESIS


def _edit_descriptors(records: list[dict]) -> list[dict]:
    descriptors = []
    for record in records:
        payload = record["payload"]
        meta = payload.get("meta")
        edited = meta.get("edited") if type(meta) is dict else None
        tool = meta.get("tool") if type(meta) is dict else None
        if (record.get("kind") != "ledger"
                or payload.get("kind") != "tool_result"
                or type(meta) is not dict
                or type(tool) is not str
                or tool not in {"write_file", "edit_file", "apply_patch"}
                or meta.get("ok") is not True
                or type(edited) is not dict or not edited
                or any(type(key) is not str or not _sha(value)
                       for key, value in edited.items())):
            continue
        descriptors.append({
            "kind": "tool_result_edit_fingerprint",
            "trace_sequence": record["sequence"],
            "record_sha256": record["record_sha256"],
            "record_kind": record["kind"],
            "payload_kind": payload["kind"],
            "json_pointer": "/payload/meta/edited",
            "value_sha256": canonical_sha256(edited),
        })
    return descriptors


def _unavailable(record: dict, pointer: str, reason: str, block: object) -> dict:
    result = {"status": "unavailable", "reason": reason,
              "trace_sequence": record["sequence"],
              "record_sha256": record["record_sha256"],
              "record_kind": record["kind"],
              "json_pointer": pointer}
    try:
        result["value_sha256"] = canonical_sha256(block)
    except Exception:
        pass
    return result


def _action_witness(records: list[dict]) -> dict:
    for record in records:
        block = record["payload"].get("action_witness")
        if block is None:
            continue
        if record["kind"] != "result":
            return _unavailable(record, "/payload/action_witness",
                                "UNSUPPORTED_SOURCE_RECORD_KIND", block)
        if (type(block) is dict and type(block.get("count")) is int
                and block["count"] >= 0 and _sha(block.get("head_sha256"))):
            return {"status": "present",
                    "kind": "reported_action_witness_summary",
                    "trace_sequence": record["sequence"],
                    "record_sha256": record["record_sha256"],
                    "record_kind": record["kind"],
                    "payload_kind": "result",
                    "value_sha256": canonical_sha256(block),
                    "count": block["count"],
                    "head_sha256": block["head_sha256"],
                    "json_pointer": "/payload/action_witness"}
        return _unavailable(record, "/payload/action_witness",
                            "UNSUPPORTED_BLOCK_SHAPE", block)
    return {"status": "absent"}


def _tool_receipts(records: list[dict]) -> dict:
    for record in records:
        block = record["payload"].get("tool_call_receipts")
        if block is None:
            continue
        if record["kind"] != "result":
            return _unavailable(record, "/payload/tool_call_receipts",
                                "UNSUPPORTED_SOURCE_RECORD_KIND", block)
        if (type(block) is dict and type(block.get("count")) is int
                and block["count"] >= 0
                and _sha(block.get("chain_head_sha256"))):
            return {"status": "present",
                    "kind": "reported_tool_call_receipts_summary",
                    "trace_sequence": record["sequence"],
                    "record_sha256": record["record_sha256"],
                    "record_kind": record["kind"],
                    "payload_kind": "result",
                    "value_sha256": canonical_sha256(block),
                    "count": block["count"],
                    "chain_head_sha256": block["chain_head_sha256"],
                    "json_pointer": "/payload/tool_call_receipts"}
        return _unavailable(record, "/payload/tool_call_receipts",
                            "UNSUPPORTED_BLOCK_SHAPE", block)
    return {"status": "absent"}


def derive_effect_evidence(records: list[dict], *, trace_ref: str,
                           terminal_state: str,
                           terminal_basis_event_type: str,
                           terminal_basis_event_sha256: str) -> dict:
    _validate_inputs(records, trace_ref, terminal_state,
                     terminal_basis_event_type, terminal_basis_event_sha256)
    descriptors = _edit_descriptors(records)
    visible = descriptors[:MAX_VISIBLE_OBSERVATIONS]
    return {
        "schema": SCHEMA,
        "scope": "owner_private_trace_prefix",
        "basis": {
            "trace_ref": trace_ref,
            "record_count": len(records),
            "trace_head_sha256": _trace_head(records),
            "terminal_state": terminal_state,
            "terminal_basis_event_type": terminal_basis_event_type,
            "terminal_basis_event_sha256": terminal_basis_event_sha256,
        },
        "known_observation_count": len(descriptors),
        "known_observations_omitted": len(descriptors) - len(visible),
        "known_observations_digest": canonical_sha256(descriptors),
        "known_observations": visible,
        "action_witness": _action_witness(records),
        "tool_call_receipts": _tool_receipts(records),
        "unknown_effect_scope": list(_UNKNOWN_SCOPE),
        "does_not_prove": list(_DOES_NOT_PROVE),
    }


def validate_effect_evidence(records: list[dict], *, trace_ref: str,
                             terminal_state: str,
                             terminal_basis_event_type: str,
                             terminal_basis_event_sha256: str,
                             submitted: dict) -> None:
    try:
        if type(submitted) is not dict:
            raise EffectEvidenceError()
        canonical_bytes(submitted)
        expected = derive_effect_evidence(
            records,
            trace_ref=trace_ref,
            terminal_state=terminal_state,
            terminal_basis_event_type=terminal_basis_event_type,
            terminal_basis_event_sha256=terminal_basis_event_sha256,
        )
        if canonical_bytes(submitted) != canonical_bytes(expected):
            raise EffectEvidenceError()
    except EffectEvidenceError:
        raise
    except Exception:
        raise EffectEvidenceError() from None
