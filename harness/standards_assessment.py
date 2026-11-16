"""Deterministic applicability and crosswalk assessment for standards profiles."""
from __future__ import annotations

from datetime import date
from typing import Any

from .governance.control_baseline import CONTROL_TIERS
from .standards_profile import validate_profile_object
from .standards_schema import parse_date

ASSESSMENT_SCHEMA = "flywheel.standards-assessment/v1"
_SELECTOR_CONTEXT = {
    "jurisdictions": "jurisdiction",
    "operator_roles": "operator_role",
    "covered_uses": "covered_use",
}


def _parse_as_of(value: str) -> tuple[date | None, list[dict[str, str]]]:
    class _C:
        def __init__(self) -> None:
            self.errors: list[dict[str, str]] = []
            self.gaps: list[dict[str, str]] = []

        def error(self, path: str, code: str, message: str) -> None:
            self.errors.append({"path": path, "code": code, "message": message})

        def gap(self, path: str, code: str, message: str) -> None:
            self.gaps.append({"path": path, "code": code, "message": message})

    c = _C()
    parsed = parse_date(value, "$.as_of", c)  # type: ignore[arg-type]
    return parsed, c.errors


def _known_control_ids(context: dict[str, Any]) -> set[str]:
    return {f"tadr:{tier}:{slug}" for slug, tier in CONTROL_TIERS.items()}


def _gap_codes(validation: dict[str, Any]) -> list[str]:
    return [str(g["code"]) for g in validation.get("gaps", [])]


def _source_status(profile: dict[str, Any], as_of: date) -> str:
    effective = profile["effective"]
    start = date.fromisoformat(effective["effective_from"])
    end = effective.get("effective_to")
    if as_of < start:
        return "not_yet_effective"
    if end is not None and as_of > date.fromisoformat(end):
        return "expired"
    if effective.get("superseded_by") or \
            profile["provenance"]["source_status"] == "superseded":
        return "superseded"
    return profile["provenance"]["source_status"]


def _binding_allows_superseded(profile: dict[str, Any]) -> bool:
    instrument = profile["instrument"]
    return instrument["binding_review_status"] == "accepted_pinned_basis"


def _context_value(context: dict[str, Any], key: str) -> Any:
    value = context.get(key)
    if value in ("", "unknown"):
        return None
    return value


def _conflict_selectors(context: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in context.get("conflicting_facts", []) or []:
        if isinstance(item, dict) and isinstance(item.get("selector"), str):
            out.append({"selector": item["selector"]})
    return out


def _selector_status(req: dict[str, Any], context: dict[str, Any],
                     conflicts: list[dict[str, str]]) -> tuple[str, list[dict]]:
    conflict_names = {c["selector"] for c in conflicts}
    for profile_key, context_key in _SELECTOR_CONTEXT.items():
        if profile_key in conflict_names or context_key in conflict_names:
            return "conflict", [{"selector": context_key,
                                 "reason": "conflicting_fact"}]
    for profile_key, context_key in _SELECTOR_CONTEXT.items():
        expected = req["selectors"][profile_key]
        supplied = _context_value(context, context_key)
        if supplied is None:
            return "needs_review", [{
                "selector": context_key,
                "expected": expected,
                "supplied": None,
                "reason": "missing_fact",
            }]
        supplied_values = supplied if isinstance(supplied, list) else [supplied]
        if "*" in expected:
            continue
        if not any(value in expected for value in supplied_values):
            return "does_not_apply_with_reason", [{
                "selector": context_key,
                "expected": expected,
                "supplied": supplied,
                "reason": "selector_mismatch",
            }]
    return "applies", []


def _mapping(req: dict[str, Any], known: set[str]) -> dict[str, Any]:
    unknown = sorted(c for c in req.get("maps_to_controls", [])
                     if c not in known)
    return {"valid": not unknown, "unrecognized_controls": unknown}


def _requirement_result(req: dict[str, Any], context: dict[str, Any],
                        *, known: set[str], source_status: str,
                        profile: dict[str, Any],
                        conflicts: list[dict[str, str]]) -> dict[str, Any]:
    status, reasons = _selector_status(req, context, conflicts)
    gaps: list[str] = []
    if source_status == "not_yet_effective":
        status = "does_not_apply_with_reason"
        reasons = [{"selector": "as_of", "expected": [
            profile["effective"]["effective_from"]],
            "supplied": context.get("as_of"),
            "reason": "not_yet_effective"}]
    elif source_status == "expired":
        status = "needs_review"
        reasons = [{"selector": "as_of",
                    "expected": [profile["effective"]["effective_to"]],
                    "supplied": context.get("as_of"),
                    "reason": "source_expired"}]
        gaps.append("source_expired")
    elif source_status == "superseded" and not _binding_allows_superseded(profile):
        status = "needs_review"
        reasons = [{"selector": "binding_review_status",
                    "expected": ["accepted_pinned_basis"],
                    "supplied": profile["instrument"]["binding_review_status"],
                    "reason": "superseded_source_requires_binding_review"}]
    elif source_status == "superseded":
        gaps.append("binding_review_not_independently_verified")
    mapping = _mapping(req, known)
    if not mapping["valid"]:
        gaps.append("unrecognized_control_mapping")
    evidence = dict(req["evidence"])
    if evidence["status"] not in ("observed", "independently_reproduced"):
        gaps.append(f"{evidence['status']}_evidence")
    return {
        "requirement_id": req["requirement_id"],
        "requirement_ref": req["requirement_ref"],
        "applicability": status,
        "applicability_basis": "declared_profile_facts",
        "reasons": reasons,
        "source_status": source_status,
        "mapping": mapping,
        "evidence": evidence,
        "gaps": gaps,
        "does_not_prove": req["does_not_prove"],
    }


def assess_profile(profile: object, context: object, *, as_of: str) -> dict[str, Any]:
    validation = validate_profile_object(profile)
    as_of_date, as_of_errors = _parse_as_of(as_of)
    if validation["verdict"] == "INVALID" or as_of_errors:
        return {
            "schema": ASSESSMENT_SCHEMA,
            "verdict": "INVALID",
            "profile": None,
            "as_of": as_of,
            "source": None,
            "requirements": [],
            "gaps": _gap_codes(validation),
            "conflicts": [],
            "validation": validation,
            "errors": validation["errors"] + as_of_errors,
            "does_not_prove": (
                "No assessment was made; invalid inputs do not prove "
                "compliance, certification, or approval."),
        }
    if not isinstance(profile, dict) or not isinstance(context, dict):
        return {
            "schema": ASSESSMENT_SCHEMA,
            "verdict": "INVALID",
            "profile": None,
            "as_of": as_of,
            "source": None,
            "requirements": [],
            "gaps": _gap_codes(validation),
            "conflicts": [],
            "validation": validation,
            "errors": [{"path": "$.context", "code": "type",
                        "message": "context must be an object"}],
            "does_not_prove": "Invalid inputs do not prove compliance.",
        }
    context_for_eval = dict(context)
    context_for_eval["as_of"] = as_of
    source_status = _source_status(profile, as_of_date)  # type: ignore[arg-type]
    gaps = _gap_codes(validation)
    if source_status == "superseded" and _binding_allows_superseded(profile):
        gaps.append("binding_review_not_independently_verified")
    elif source_status == "superseded":
        gaps.append("binding_review_required_for_superseded_source")
    conflicts = _conflict_selectors(context)
    known = _known_control_ids(context)
    requirements = [
        _requirement_result(req, context_for_eval, known=known,
                            source_status=source_status, profile=profile,
                            conflicts=conflicts)
        for req in profile["requirements"]
    ]
    if conflicts or any(r["applicability"] == "conflict" for r in requirements):
        verdict = "CONFLICT"
    elif gaps or any(r["applicability"] == "needs_review" or r["gaps"]
                    for r in requirements):
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "REVIEWABLE"
    return {
        "schema": ASSESSMENT_SCHEMA,
        "verdict": verdict,
        "profile": {
            "profile_id": profile["profile_id"],
            "version": profile["version"],
        },
        "as_of": as_of,
        "source": {
            "status": source_status,
            "reported_status": profile["provenance"]["source_status"],
            "reported_binding_review_status": (
                profile["instrument"]["binding_review_status"]),
            "verification": "caller_reported_not_independently_verified",
        },
        "requirements": requirements,
        "gaps": gaps,
        "conflicts": conflicts,
        "validation": validation,
        "does_not_prove": (
            "This assessment evaluates declared applicability facts and "
            "crosswalk shape only; it does not prove legal compliance, "
            "requirement truth, certification, approval, or sufficiency."),
    }
