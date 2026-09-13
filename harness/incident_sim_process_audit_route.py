"""HTTP review route for incident-sim process-audit packets."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from harness.evidence_json import strict_load_json
from harness.evidence_public import ERROR_SCHEMA, TransportError, error_response
from harness.incident_sim_packet import SCHEMA as PACKET_SCHEMA
from harness.incident_sim_packet_verify import (
    MATCH,
    NOT_ASSESSED,
    verify_process_audit_packet,
)

PATH = "/api/incident-sim/process-audit/review"
REVIEW_SCHEMA = "flywheel.incident-sim-process-audit-review/v1"
MAX_PACKET_BYTES = 1_048_576

_DOES_NOT_PROVE = [
    "semantic correctness of the task, trace, evaluation, scorer, or access claim",
    "external authority, wall-clock truth, disclosure completeness, or immutable history",
    "absence of a coherent rewrite of the local packet and every packet-local digest",
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
        packet = strict_load_json(data, max_bytes=MAX_PACKET_BYTES, max_depth=64)
        if packet.get("schema") != PACKET_SCHEMA:
            raise TransportError(
                "INVALID_PACKET",
                "request body is not an incident-sim process-audit packet",
                422,
            )
        verification = verify_process_audit_packet(packet)
        verdict = verification.get("verdict")
        body = {
            "schema": REVIEW_SCHEMA,
            "source": {
                "format": "incident-sim-process-audit-json",
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_length": len(data),
            },
            "assessment": (
                "packet-local-match" if verdict == "MATCH"
                else "packet-local-drift"
            ),
            "semantic_verification": "UNVERIFIABLE",
            "verification": verification,
            "declared_access": _declared_access(packet, verification),
            "source_pointers": _source_pointers(packet),
            "does_not_prove": list(_DOES_NOT_PROVE),
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


def _add(rows: list[dict[str, Any]], packet: dict[str, Any],
         pointer: str, *keys: str) -> None:
    node: Any = packet
    for key in keys:
        if type(node) is not dict or key not in node:
            return
        node = node[key]
    rows.append({"json_pointer": pointer, "source_value": _snapshot(node)})


def _source_pointers(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("schema", "task_sha256", "trace_sha256",
                "evaluation_sha256", "packet_sha256"):
        _add(rows, packet, f"/{key}", key)
    _add(rows, packet, "/evaluation/overall/verdict",
         "evaluation", "overall", "verdict")
    _add(rows, packet, "/source_values", "source_values")
    _add(rows, packet, "/independence", "independence")
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
    for item in assessment.get("does_not_prove", []):
        limits.append(str(item))
    return {
        "verdict": verdict,
        "coverage_assessment": checked,
        "reported_coverage_assessment": reported,
        "limits": limits,
    }
