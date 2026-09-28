"""Declared institutional evidence-access consistency checks.

This module checks only the consistency and coverage of a caller-declared access
record against retained source data. It does not prove wall-clock truth,
disclosure completeness, semantic correctness, or immutable external history.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .evidence_json import canonical_bytes, canonical_sha256

SCHEMA = "flywheel.institutional-access/v1"
SCOPE_SCHEMA = "flywheel.institutional-access-scope/v1"
ASSESSMENT_SCHEMA = "flywheel.institutional-access-assessment/v1"
STATUSES = frozenset({"requested", "granted", "denied", "unavailable", "unknown", "withdrawn"})
REDACTION_IMPACTS = frozenset({"none", "weakens_coverage", "blocks_verification", "unknown"})
_LIMITING_IMPACTS = frozenset({"weakens_coverage", "blocks_verification", "unknown"})
_DOES_NOT_PROVE = [
    "semantic correctness of the evaluated claim or scorer",
    "wall-clock truth, disclosure completeness, or immutable external history",
    "absence of undeclared evidence, withdrawals, restrictions, or contests",
    "authenticity of the declaring institution beyond retained source consistency",
]
_MAX_TEXT, _MAX_EVENTS, _MAX_POINTERS = 512, 128, 32


class InstitutionalAccessError(ValueError):
    """Raised when a declared institutional access record is malformed."""


def _err(message: str) -> None:
    raise InstitutionalAccessError(message)


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TEXT or any(ord(c) < 32 for c in value):
        _err(f"{name} must be a bounded non-empty string")
    return value


def _string_list(value: object, name: str, *, nonempty: bool = False) -> list[str]:
    if type(value) is not list or (nonempty and not value):
        _err(f"{name} must be a{' non-empty' if nonempty else ''} list")
    out = [_text(item, name) for item in value]
    if len(out) != len(set(out)):
        _err(f"{name} must not contain duplicates")
    return out


def _snapshot(value: object) -> object:
    return json.loads(canonical_bytes(value).decode("utf-8"))


def _inventory(sources: Mapping[str, object]) -> list[dict[str, str]]:
    if not isinstance(sources, Mapping) or not sources:
        _err("source inventory requires retained sources")
    rows = []
    for ref, value in sources.items():
        rows.append({"source_ref": _text(ref, "source_ref"), "sha256": canonical_sha256(value)})
    refs = [row["source_ref"] for row in rows]
    if len(refs) != len(set(refs)):
        _err("source inventory contains duplicate refs")
    return sorted(rows, key=lambda row: row["source_ref"])


def _claim_rows(claims: object, source_refs: set[str]) -> list[dict[str, Any]]:
    if type(claims) is not list or not claims:
        _err("claims must be a non-empty list")
    rows, seen = [], set()
    for claim in claims:
        if type(claim) is not dict or set(claim) != {"claim_id", "required_refs"}:
            _err("claims are malformed")
        claim_id = _text(claim["claim_id"], "claim_id")
        if claim_id in seen:
            _err("duplicate claim_id")
        seen.add(claim_id)
        required = sorted(_string_list(claim["required_refs"], "required_refs", nonempty=True))
        if any(ref not in source_refs for ref in required):
            _err("required ref is absent from source inventory")
        rows.append({"claim_id": claim_id, "required_refs": required})
    return sorted(rows, key=lambda row: row["claim_id"])


def access_scope(scope_id: str, claims: Mapping[str, list[str]], sources: Mapping[str, object]) -> dict[str, Any]:
    """Bind claim required refs to the retained source inventory."""
    inventory = _inventory(sources)
    if not isinstance(claims, Mapping) or not claims:
        _err("claims must be a non-empty mapping")
    raw_claims = [{"claim_id": claim_id, "required_refs": refs}
                  for claim_id, refs in claims.items()]
    claim_rows = _claim_rows(raw_claims, {row["source_ref"] for row in inventory})
    body = {"schema": SCOPE_SCHEMA, "scope_id": _text(scope_id, "scope_id"),
            "claims": claim_rows, "source_inventory": inventory}
    return {**body, "scope_sha256": canonical_sha256(body)}


def _check_scope(scope: dict[str, Any], sources: Mapping[str, object]) -> None:
    if type(scope) is not dict or set(scope) != {"schema", "scope_id", "claims", "source_inventory", "scope_sha256"}:
        _err("scope is malformed")
    inventory = _inventory(sources)
    if scope.get("source_inventory") != inventory:
        _err("source inventory drift")
    claims = _claim_rows(scope.get("claims"), {row["source_ref"] for row in inventory})
    if scope["claims"] != claims:
        _err("claims are not normalized")
    claimed = scope["scope_sha256"]
    body = {key: scope[key] for key in ("schema", "scope_id", "claims", "source_inventory")}
    if scope.get("schema") != SCOPE_SCHEMA or claimed != canonical_sha256(body):
        _err("scope_sha256 mismatch")


def _decode_token(raw: str) -> str:
    index = 0
    while index < len(raw):
        if raw[index] == "~":
            if index + 1 >= len(raw) or raw[index + 1] not in "01":
                _err("json_pointer is invalid")
            index += 2
        else:
            index += 1
    return raw.replace("~1", "/").replace("~0", "~")


def _pointer(source: object, pointer: str) -> object:
    if type(pointer) is not str or (pointer and not pointer.startswith("/")):
        _err("json_pointer is invalid")
    node = source
    if pointer == "":
        return node
    for raw in pointer[1:].split("/"):
        part = _decode_token(raw)
        if type(node) is list:
            if not part.isascii() or not part.isdecimal() or str(int(part)) != part or int(part) >= len(node):
                _err("json_pointer is invalid")
            node = node[int(part)]
        else:
            if type(node) is not dict or part not in node:
                _err("json_pointer is invalid")
            node = node[part]
    return node


def _reviewer(value: object) -> dict[str, Any]:
    keys = {"role", "declared_conflicts", "relationship_to_producer"}
    if type(value) is not dict or set(value) != keys:
        _err("reviewer is malformed")
    return {"role": _text(value["role"], "role"),
            "declared_conflicts": _string_list(value["declared_conflicts"], "declared_conflicts"),
            "relationship_to_producer": _text(value["relationship_to_producer"], "relationship_to_producer")}


def _event(value: object, sources: Mapping[str, object], source_refs: set[str]) -> dict[str, Any]:
    keys = {"event_id", "sequence", "evidence_ref", "status", "stated_reason", "source_pointers", "redactions"}
    if type(value) is not dict or set(value) != keys:
        _err("access event is malformed")
    sequence = value["sequence"]
    if isinstance(sequence, bool) or type(sequence) is not int or sequence < 1:
        _err("event sequence must be a positive integer")
    ref = _text(value["evidence_ref"], "evidence_ref")
    if ref not in source_refs:
        _err("event evidence_ref is absent from source inventory")
    status = value["status"]
    if status not in STATUSES:
        _err("event status is invalid")
    pointers = value["source_pointers"]
    if type(pointers) is not list or len(pointers) > _MAX_POINTERS:
        _err("source_pointers is malformed")
    checked_pointers = []
    for pointer in pointers:
        if type(pointer) is not dict or set(pointer) != {"source_ref", "json_pointer", "source_value"}:
            _err("source pointer is malformed")
        if pointer["source_ref"] != ref:
            _err("source pointer ref must match event evidence_ref")
        observed = _pointer(sources[ref], pointer["json_pointer"])
        if canonical_sha256(observed) != canonical_sha256(pointer["source_value"]):
            _err("source pointer value mismatch")
        checked_pointers.append({"source_ref": pointer["source_ref"],
                                 "json_pointer": pointer["json_pointer"],
                                 "source_value": _snapshot(pointer["source_value"])})
    redactions = value["redactions"]
    if type(redactions) is not list or len(redactions) > _MAX_POINTERS:
        _err("redactions is malformed")
    checked_redactions = []
    for redaction in redactions:
        if type(redaction) is not dict or set(redaction) != {"redaction_id", "impact", "stated_reason"}:
            _err("redaction is malformed")
        if redaction["impact"] not in REDACTION_IMPACTS:
            _err("redaction impact is invalid")
        checked_redactions.append({"redaction_id": _text(redaction["redaction_id"], "redaction_id"),
                                  "impact": redaction["impact"],
                                  "stated_reason": _text(redaction["stated_reason"], "stated_reason")})
    return {"event_id": _text(value["event_id"], "event_id"), "sequence": sequence,
            "evidence_ref": ref, "status": status,
            "stated_reason": _text(value["stated_reason"], "stated_reason"),
            "source_pointers": checked_pointers, "redactions": checked_redactions}


def _normalize_events(events: object, sources: Mapping[str, object], source_refs: set[str]) -> list[dict[str, Any]]:
    if type(events) is not list or len(events) > _MAX_EVENTS:
        _err("events must be a bounded list")
    out = [_event(item, sources, source_refs) for item in events]
    event_ids = [item["event_id"] for item in out]
    sequences = [item["sequence"] for item in out]
    if len(event_ids) != len(set(event_ids)) or len(sequences) != len(set(sequences)):
        _err("event history contains duplicate ids or sequences")
    return sorted(out, key=lambda item: item["sequence"])


def _claim_reports(scope: dict[str, Any], latest: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    reports = []
    for claim in scope["claims"]:
        available, limited, reasons = [], [], []
        for ref in claim["required_refs"]:
            event = latest.get(ref)
            if event is None:
                limited.append(ref); reasons.append(f"{ref}:missing_access_event"); continue
            if event["status"] != "granted":
                limited.append(ref); reasons.append(f"{ref}:{event['status']}"); continue
            if not event["source_pointers"]:
                limited.append(ref); reasons.append(f"{ref}:missing_source_pointer"); continue
            impacts = [r["impact"] for r in event["redactions"] if r["impact"] in _LIMITING_IMPACTS]
            if impacts:
                limited.append(ref); reasons.extend(f"{ref}:redaction:{impact}" for impact in impacts); continue
            available.append(ref)
        coverage = "complete" if not limited else ("unverifiable" if not available else "limited")
        reports.append({"claim_id": claim["claim_id"], "coverage": coverage,
                        "available_refs": available, "limited_refs": limited,
                        "reasons": reasons})
    return reports


def assess_institutional_access(record: dict[str, Any] | None, *, scope: dict[str, Any],
                                sources: Mapping[str, object]) -> dict[str, Any] | None:
    """Assess declared access coverage against a retained source scope.

    ``None`` means the caller supplied no institutional-access component and no
    access assessment is available.
    """
    if record is None:
        return None
    _check_scope(scope, sources)
    if type(record) is not dict or set(record) != {"schema", "scope_sha256", "reviewer", "events"}:
        _err("institutional access record is malformed")
    if record.get("schema") != SCHEMA or record.get("scope_sha256") != scope["scope_sha256"]:
        _err("scope_sha256 mismatch")
    source_refs = {row["source_ref"] for row in scope["source_inventory"]}
    events = _normalize_events(record["events"], sources, source_refs)
    latest = {event["evidence_ref"]: event for event in events}
    claims = _claim_reports(scope, latest)
    verdicts = {claim["coverage"] for claim in claims}
    overall = "complete" if verdicts == {"complete"} else ("unverifiable" if verdicts == {"unverifiable"} else "limited")
    return {"schema": ASSESSMENT_SCHEMA, "scope_sha256": scope["scope_sha256"],
            "coverage_assessment": overall, "reviewer": _reviewer(record["reviewer"]),
            "claims": claims, "events": events,
            "latest_by_ref": [{"evidence_ref": ref, "event_id": event["event_id"], "status": event["status"]}
                              for ref, event in sorted(latest.items())],
            "does_not_prove": list(_DOES_NOT_PROVE)}
