"""HTTP review route for incident-sim process-audit packets."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from harness.evidence_json import strict_load_json
from harness.evidence_public import ERROR_SCHEMA, TransportError, error_response
from harness.gateway_effect_offline import trace_export_preview
from harness.incident_sim_packet import SCHEMA as PACKET_SCHEMA
from harness.incident_sim_packet_verify import (
    MATCH,
    NOT_ASSESSED,
    verify_process_audit_packet,
)
from harness.scope import LEGACY_SCOPE_KEY, scope_key, scope_list

PATH = "/api/incident-sim/process-audit/review"
# v2 reviews name the coverage list `scope`; v1 reviews carried the older key.
REVIEW_SCHEMA_V1 = "flywheel.incident-sim-process-audit-review/v1"
REVIEW_SCHEMA = "flywheel.incident-sim-process-audit-review/v2"
REVIEW_REQUEST_SCHEMA = "flywheel.incident-sim-process-audit-review-request/v1"
MAX_PACKET_BYTES = 1_048_576

_REVIEW_SCOPE = [
    "packet-local digests, receipt seals and receipt chains were rechecked; "
    "task, trace, evaluation and access content is taken as submitted",
    "authority, times and disclosures are taken as the packet declares them",
    "a coherent rewrite of the packet with every packet-local digest recomputed "
    "rechecks the same way",
]


def is_json_content_type(value: str | None) -> bool:
    media = (value or "").split(";", 1)[0].strip().lower()
    return media == "application/json"


def payload_too_large_response() -> tuple[dict, int]:
    return error_response(TransportError(
        "PAYLOAD_TOO_LARGE",
        "process-audit packet exceeds the 1 MiB request limit",
        413,
    ))


def unsupported_media_type_response() -> tuple[dict, int]:
    return error_response(TransportError(
        "UNSUPPORTED_MEDIA_TYPE",
        "process-audit review requires application/json",
        415,
    ))


def process_audit_review_post(
    path: str,
    raw: bytes | str,
    *,
    content_type: str | None,
) -> tuple[dict, int]:
    """Review one submitted packet without persistence or external calls."""
    try:
        if path != PATH:
            raise TransportError("NOT_FOUND", "unknown incident-sim route", 404)
        if not is_json_content_type(content_type):
            return unsupported_media_type_response()
        data = raw.encode("utf-8", "strict") if isinstance(raw, str) else raw
        if type(data) is not bytes:
            raise TransportError("INVALID_JSON", "request body is not strict JSON")
        if len(data) > MAX_PACKET_BYTES:
            return payload_too_large_response()
        request = strict_load_json(data, max_bytes=MAX_PACKET_BYTES, max_depth=64)
        packet, expected_hashes, source_format = _review_input(request)
        if packet.get("schema") != PACKET_SCHEMA:
            raise TransportError(
                "INVALID_PACKET",
                "request body is not an incident-sim process-audit packet",
                422,
            )
        verification = verify_process_audit_packet(
            packet, expected_hashes=expected_hashes)
        verdict = verification.get("packet_local_verdict", verification.get("verdict"))
        body = {
            "schema": REVIEW_SCHEMA,
            "source": {
                "format": source_format,
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_length": len(data),
            },
            "assessment": (
                "packet-local-match" if verdict == "MATCH"
                else "packet-local-drift"
            ),
            "semantic_verification": "UNVERIFIABLE",
            "verification": verification,
            "gateway_effect_verification": verification["gateway_effect_verification"],
            "declared_access": _declared_access(packet, verification),
            "source_pointers": _source_pointers(packet),
            "scope": list(_REVIEW_SCOPE),
        }
        return body, 200
    except TransportError as exc:
        return error_response(exc)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return ({"schema": ERROR_SCHEMA,
                 "error": {"code": "INVALID_JSON",
                           "message": "request body is not strict JSON"}}, 400)


def _snapshot(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _review_input(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    if request.get("schema") == REVIEW_REQUEST_SCHEMA:
        packet = request.get("packet")
        expected = request.get("expected_hashes")
        if type(packet) is not dict or (expected is not None and type(expected) is not dict):
            raise TransportError("INVALID_PACKET", "review request is malformed", 422)
        return packet, expected, "incident-sim-process-audit-review-request-json"
    return request, None, "incident-sim-process-audit-json"


def _add(rows: list[dict[str, Any]], packet: dict[str, Any],
         pointer: str, *keys: str) -> None:
    node: Any = packet
    for key in keys:
        if type(node) is not dict or key not in node:
            return
        node = node[key]
    rows.append({"json_pointer": pointer, "source_value": _snapshot(node)})


def _add_gateway_preview(rows: list[dict[str, Any]], packet: dict[str, Any]) -> None:
    component = packet.get("gateway_effect")
    if type(component) is not dict:
        return
    rows.append({
        "json_pointer": "/gateway_effect/trace_preview",
        "source": "derived_from_submitted_trace_records",
        "privacy": "content_free_preview",
        "source_value": trace_export_preview(component.get("trace_records")),
        "limits": ["full trace_records are private exact-review input"],
    })


def _source_pointers(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("schema", "task_sha256", "trace_sha256",
                "evaluation_sha256", "packet_sha256"):
        _add(rows, packet, f"/{key}", key)
    _add(rows, packet, "/evaluation/overall/verdict",
         "evaluation", "overall", "verdict")
    _add(rows, packet, "/source_values", "source_values")
    _add(rows, packet, "/independence", "independence")
    _add_gateway_preview(rows, packet)
    _add(rows, packet, "/gateway_effect/packet_local_sha256",
         "gateway_effect", "packet_local_sha256")
    _add(rows, packet, "/gateway_effect/terminal_result/state",
         "gateway_effect", "terminal_result", "state")
    _add(rows, packet, "/institutional_access/assessment/coverage_assessment",
         "institutional_access", "assessment", "coverage_assessment")
    _add(rows, packet, "/institutional_access/assessment/claims",
         "institutional_access", "assessment", "claims")
    _add(rows, packet, "/institutional_access/assessment/latest_by_ref",
         "institutional_access", "assessment", "latest_by_ref")
    _add(rows, packet, "/institutional_access/assessment/reviewer",
         "institutional_access", "assessment", "reviewer")
    return rows


def _declared_access(packet: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    verdict = str(verification.get("institutional_access_verdict", "DRIFT"))
    component = packet.get("institutional_access")
    if verdict == NOT_ASSESSED or type(component) is not dict:
        return {
            "verdict": NOT_ASSESSED,
            "coverage_assessment": "not_assessed",
            "limits": [
                "institutional_access component absent; declared access coverage was not assessed",
            ],
        }
    assessment = component.get("assessment")
    if type(assessment) is not dict:
        return {"verdict": verdict, "coverage_assessment": "unknown",
                "limits": ["institutional_access assessment is malformed"]}
    reported = str(assessment.get("coverage_assessment", "unknown"))
    checked = reported if verdict == MATCH else "unknown"
    limits: list[str] = []
    if verdict != MATCH:
        limits.append(
            "institutional_access component failed packet-local verification; reported coverage is untrusted"
        )
    for claim in assessment.get("claims", []):
        if type(claim) is dict and claim.get("coverage") != "complete":
            claim_id = str(claim.get("claim_id", "unknown"))
            reasons = claim.get("reasons", [])
            detail = ",".join(str(item) for item in reasons) or "coverage_limited"
            limits.append(f"{claim_id}:{detail}")
    declared = {"verdict": verdict, "coverage_assessment": checked,
                "reported_coverage_assessment": reported, "limits": limits}
    # A v1 assessment's older list is a list of limits; a v2 list says what it covers.
    if scope_key(assessment) == LEGACY_SCOPE_KEY:
        limits.extend(scope_list(assessment))
    elif scope_list(assessment):
        declared["scope"] = scope_list(assessment)
    return declared
