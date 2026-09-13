"""Offline gateway-effect verification over submitted terminal evidence."""
from __future__ import annotations
import base64
import binascii
from collections import Counter
from typing import Any
from .evidence_json import canonical_bytes, canonical_sha256
from .gateway_agent_projection import SCHEMA as PROJECTION_SCHEMA, validate_projection
from .gateway_agent_trace import GENESIS, KINDS, MAX_RECORDS, SCHEMA as TRACE_SCHEMA
from .gateway_effect_evidence import validate_effect_evidence
from .gateway_operation_validation import (LIFECYCLE, OPERATION_REF_PATTERN, TERMINAL_EVENTS,
    validate_history, validate_result)
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN, validate_event
from .operation_grants import OWNER_REF_PATTERN
SCHEMA = "flywheel.gateway-effect-offline-component/v1"
VERIFY_SCHEMA = "flywheel.gateway-effect-offline-verification/v1"
MATCH = "MATCH"
DRIFT = "DRIFT"
UNAVAILABLE = "UNAVAILABLE"
UNVERIFIABLE = "UNVERIFIABLE"
_EXPECTED = {"terminal_result_sha256": "terminal_result",
             "lifecycle_history_sha256": "lifecycle_history",
             "trace_records_sha256": "trace_records"}
_SEMANTIC_LIMITS = ["semantic correctness",
                    "producer identity or independent execution truth",
                    "absence of unrecorded effects", "safety or rollback"]
class _Fail(ValueError):
    pass
def _snapshot(value: object) -> object:
    return __import__("json").loads(canonical_bytes(value).decode("utf-8"))
def _sha(value: object) -> bool:
    return type(value) is str and SHA256_PATTERN.fullmatch(value) is not None
def _trace_ref(owner_ref: str, journey_ref: str, operation_ref: str) -> str:
    return "agt_" + canonical_sha256({
        "owner_ref": owner_ref,
        "journey_ref": journey_ref,
        "operation_ref": operation_ref,
    })[:32]
def trace_export_preview(records: object) -> dict[str, Any]:
    """Return content-free trace shape for export review."""
    if type(records) is not list:
        return {"record_count": 0, "record_kinds": {},
                "total_canonical_bytes": 0, "max_record_bytes": 0,
                "sensitive_payload_categories": ["MALFORMED"]}
    sizes, kinds, categories = [], Counter(), set()
    for record in records:
        try:
            sizes.append(len(canonical_bytes(record)))
        except Exception:
            sizes.append(0)
            categories.add("MALFORMED")
        kind = record.get("kind") if type(record) is dict else None
        if kind not in KINDS:
            kind = "malformed"
            categories.add("MALFORMED")
        kinds[kind] += 1
        payload = record.get("payload") if type(record) is dict else None
        if type(payload) is dict:
            if "content" in payload:
                categories.add("PRIVATE_TEXT")
            meta = payload.get("meta")
            if type(meta) is dict and "edited" in meta:
                categories.add("EDIT_FINGERPRINTS")
            if "action_witness" in payload:
                categories.add("REPORTED_ACTION_WITNESS")
            if "tool_call_receipts" in payload:
                categories.add("REPORTED_TOOL_RECEIPTS")
    return {
        "record_count": len(records),
        "record_kinds": dict(sorted(kinds.items())),
        "total_canonical_bytes": sum(sizes),
        "max_record_bytes": max(sizes, default=0),
        "sensitive_payload_categories": sorted(categories),
    }
def _record_b64(records: list[dict]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        rows.append({
            "sequence": record.get("sequence"),
            "record_sha256": record.get("record_sha256"),
            "canonical_base64": base64.b64encode(canonical_bytes(body)).decode("ascii"),
        })
    return rows
def build_gateway_effect_component(*, terminal_result: dict,
        lifecycle_history: list[dict], trace_records: list[dict]) -> dict[str, Any]:
    terminal = _snapshot(terminal_result)
    lifecycle = _snapshot(lifecycle_history)
    records = _snapshot(trace_records)
    body = {
        "schema": SCHEMA,
        "terminal_result": terminal,
        "lifecycle_history": lifecycle,
        "trace_records": records,
        "trace_preview": trace_export_preview(records),
        "trace_record_canonical_base64": _record_b64(records),
        "packet_local_sha256": {
            "terminal_result": canonical_sha256(terminal),
            "lifecycle_history": canonical_sha256(lifecycle),
            "trace_records": canonical_sha256(records),
        },
        "packet_digest_limit": (
            "packet-local digests bind submitted bytes only; they do not prove "
            "independent custody, producer identity or execution truth"
        ),
    }
    body["component_sha256"] = canonical_sha256(body)
    return body
def _validate_records(records: object, owner_ref: str, journey_ref: str,
        operation_ref: str) -> dict[str, Any]:
    if type(records) is not list or len(records) > MAX_RECORDS:
        raise _Fail("trace records malformed")
    head, expected_ref = GENESIS, _trace_ref(owner_ref, journey_ref, operation_ref)
    for index, record in enumerate(records):
        if type(record) is not dict:
            raise _Fail("trace record malformed")
        digest = record.get("record_sha256")
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        fields = {"schema", "owner_ref", "journey_ref", "operation_ref", "trace_ref",
                  "sequence", "kind", "prior_sha256", "payload"}
        if (set(body) != fields or record.get("schema") != TRACE_SCHEMA
                or record.get("owner_ref") != owner_ref
                or record.get("journey_ref") != journey_ref
                or record.get("operation_ref") != operation_ref
                or record.get("trace_ref") != expected_ref
                or type(record.get("sequence")) is not int
                or record["sequence"] != index
                or record.get("kind") not in KINDS
                or record.get("prior_sha256") != head
                or type(record.get("payload")) is not dict
                or not _sha(digest)
                or canonical_sha256(body) != digest):
            raise _Fail("trace record malformed")
        head = digest
    return {"trace_ref": expected_ref, "record_count": len(records),
            "trace_head_sha256": head}
def _check_optional_b64(component: dict, records: list[dict]) -> None:
    rows = component.get("trace_record_canonical_base64")
    if rows is None:
        return
    if type(rows) is not list or len(rows) != len(records):
        raise _Fail("canonical base64 malformed")
    for row, record in zip(rows, records):
        if (type(row) is not dict
                or set(row) != {"sequence", "record_sha256", "canonical_base64"}
                or row.get("sequence") != record.get("sequence")
                or row.get("record_sha256") != record.get("record_sha256")
                or type(row.get("canonical_base64")) is not str):
            raise _Fail("canonical base64 malformed")
        try:
            decoded = base64.b64decode(row["canonical_base64"], validate=True)
        except (binascii.Error, ValueError):
            raise _Fail("canonical base64 malformed") from None
        body = {key: value for key, value in record.items() if key != "record_sha256"}
        if decoded != canonical_bytes(body):
            raise _Fail("canonical base64 malformed")
def _validate_projection_shape(projection, trace_info, operation_ref, journey_ref) -> None:
    base = {k: v for k, v in projection.items() if k not in {"effect_evidence", "projection_sha256"}}
    base["projection_sha256"] = canonical_sha256(base)
    try:
        validate_projection(base, {"operation_ref": operation_ref, "journey_ref": journey_ref, "trace_ref": trace_info["trace_ref"]})
    except Exception:
        raise _Fail("agent projection binding mismatch") from None
    expected_hash = canonical_sha256({k: v for k, v in projection.items() if k != "projection_sha256"})
    if projection.get("projection_sha256") != expected_hash: raise _Fail("agent projection binding mismatch")
def _validate_internal(component: dict) -> tuple[dict[str, Any], dict[str, Any]]:
    terminal = component["terminal_result"]
    history = component["lifecycle_history"]
    records = component["trace_records"]
    if type(terminal) is not dict or type(history) is not list:
        raise _Fail("submitted gateway evidence malformed")
    operation_ref, action, state = (
        terminal.get("operation_ref"), terminal.get("action"), terminal.get("state"))
    if type(operation_ref) is not str or type(action) is not str or state not in {
            "completed", "failed", "cancelled"}:
        raise _Fail("terminal result malformed")
    validate_result(terminal, operation_ref, action, state)
    events = [validate_event(event) for event in history]
    if not events or any(event["event_type"] not in LIFECYCLE for event in events):
        raise _Fail("lifecycle history malformed")
    for left, right in zip(events, events[1:]):
        if right["sequence"] != left["sequence"] + 1 or right["prior_event_sha256"] != left["event_sha256"]:
            raise _Fail("lifecycle history reordered")
    validate_history(events, operation_ref)
    owner_ref, journey_ref = events[0]["actor_id"], events[0]["journey_ref"]
    if (OWNER_REF_PATTERN.fullmatch(owner_ref) is None
            or JOURNEY_REF_PATTERN.fullmatch(journey_ref) is None
            or OPERATION_REF_PATTERN.fullmatch(operation_ref) is None
            or any(event["actor_id"] != owner_ref or
                   event["journey_ref"] != journey_ref for event in events)):
        raise _Fail("gateway identity mismatch")
    terminal_event = next(event for event in events
                          if event["event_type"] in TERMINAL_EVENTS)
    basis = next((event for event in events
                  if event["event_sha256"] == terminal_event["payload"]["basis_event_sha256"]), None)
    if (terminal_event["event_type"] != f"operation_{state}"
            or terminal_event["payload"]["result_sha256"] != canonical_sha256(terminal)
            or basis is None):
        raise _Fail("terminal result binding mismatch")
    trace_info = _validate_records(records, owner_ref, journey_ref, operation_ref)
    projection = terminal["result"]
    if type(projection) is not dict or projection.get("schema") != PROJECTION_SCHEMA:
        raise _Fail("terminal result does not bind an agent projection")
    _validate_projection_shape(projection, trace_info, operation_ref, journey_ref)
    if (projection.get("state") != state
            or projection.get("record_count") != trace_info["record_count"]
            or projection.get("trace_head_sha256") != trace_info["trace_head_sha256"]):
        raise _Fail("agent projection binding mismatch")
    _check_optional_b64(component, records)
    if component.get("trace_preview") != trace_export_preview(records):
        raise _Fail("trace preview mismatch")
    if "effect_evidence" not in projection:
        return trace_info, {"verdict": UNAVAILABLE,
                            "limits": ["terminal projection has no effect_evidence"]}
    effect = projection["effect_evidence"]
    validate_effect_evidence(
        records,
        trace_ref=trace_info["trace_ref"],
        terminal_state=state,
        terminal_basis_event_type=basis["event_type"],
        terminal_basis_event_sha256=basis["event_sha256"],
        submitted=effect,
    )
    return trace_info, {"verdict": MATCH,
                        "retained_observations": effect["known_observation_count"],
                        "omitted_observations": effect["known_observations_omitted"],
                        "known_observations_digest": effect["known_observations_digest"],
                        "known_observations": effect["known_observations"],
                        "action_witness": effect["action_witness"],
                        "tool_call_receipts": effect["tool_call_receipts"],
                        "unobserved_scope": effect["unknown_effect_scope"]}
def _expected_correspondence(source: dict[str, str],
        expected_hashes: dict[str, Any] | None) -> dict[str, Any]:
    provenance = "not supplied"
    if type(expected_hashes) is dict and type(expected_hashes.get("reference_provenance")) is str:
        provenance = expected_hashes["reference_provenance"]
    checks = []
    if type(expected_hashes) is dict:
        for expected_key, source_key in _EXPECTED.items():
            expected = expected_hashes.get(expected_key)
            if expected is None:
                continue
            checks.append({
                "artifact": source_key,
                "expected_sha256": expected,
                "computed_sha256": source.get(source_key, ""),
                "verdict": MATCH if _sha(expected) and expected == source.get(source_key) else DRIFT,
            })
    verdict = (UNAVAILABLE if not checks else
               DRIFT if any(row["verdict"] == DRIFT for row in checks) else MATCH)
    return {"verdict": verdict, "reference_provenance": provenance,
            "checks": checks, "limits": [
                "matching expected hashes show correspondence with the supplied reference only",
                "they do not establish independent custody, producer identity or execution truth",
            ]}
def verify_gateway_effect_component(component: object, *,
        expected_hashes: dict[str, Any] | None = None) -> dict[str, Any]:
    if component is None:
        unavailable = {"verdict": UNAVAILABLE,
                       "limits": ["no gateway_effect component supplied"]}
        return {"schema": VERIFY_SCHEMA, "verdict": UNAVAILABLE,
                "internal_consistency": unavailable,
                "expected_correspondence": _expected_correspondence({}, expected_hashes),
                "effect_coverage": unavailable,
                "semantic_correctness": {"verdict": UNVERIFIABLE,
                                         "does_not_verify": list(_SEMANTIC_LIMITS)}}
    source: dict[str, str] = {}
    checks = []
    coverage = {"verdict": DRIFT, "limits": ["gateway_effect component failed validation"]}
    try:
        if type(component) is not dict or component.get("schema") != SCHEMA:
            raise _Fail("gateway effect component malformed")
        body = {key: value for key, value in component.items() if key != "component_sha256"}
        expected_component = canonical_sha256(body)
        checks.append({"field": "/gateway_effect", "verdict": (
            MATCH if component.get("component_sha256") == expected_component else DRIFT),
            "check": "component_sha256 excludes itself"})
        for key in _EXPECTED.values():
            source[key] = canonical_sha256(component[key])
        packet_local = component.get("packet_local_sha256")
        if type(packet_local) is not dict or any(packet_local.get(key) != value
                for key, value in source.items()):
            raise _Fail("packet-local source digests mismatch")
        trace_info, coverage = _validate_internal(component)
        checks.append({"field": "/gateway_effect/trace_records", "verdict": MATCH,
                       "check": "submitted trace records bind owner Journey operation and head"})
        internal_verdict = DRIFT if any(row["verdict"] == DRIFT for row in checks) else MATCH
    except Exception:
        internal_verdict = DRIFT
    expected = _expected_correspondence(source, expected_hashes)
    if coverage.get("verdict") == MATCH:
        coverage = {**coverage, "trace_head_sha256": trace_info["trace_head_sha256"]}
    return {"schema": VERIFY_SCHEMA,
            "verdict": internal_verdict if expected["verdict"] != DRIFT else DRIFT,
            "source_sha256": source,
            "internal_consistency": {"verdict": internal_verdict, "checks": checks},
            "expected_correspondence": expected,
            "effect_coverage": coverage,
            "semantic_correctness": {"verdict": UNVERIFIABLE,
                                     "does_not_verify": list(_SEMANTIC_LIMITS)}}
