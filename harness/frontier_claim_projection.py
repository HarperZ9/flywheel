"""frontier_claim_projection.py -- the four independent axes.

Identification owns source, proposition, and authorship. Verification
owns verdict, evidence kind, fidelity, freshness, and reproduction.
Policy owns review, community, and admission. Value owns novelty and
importance. Each axis hashes separately; unknown raw values are
preserved verbatim and named as unrecognized; no composite exists.
append_frontier_axis_event validates the typed inputs and delegates one
CAS command; it never retrieves sources or runs a checker.
"""
from __future__ import annotations

from .evidence_json import canonical_sha256
from .frontier_claim import OBSERVATION_FIELDS, SCHEMA as CLAIM_SCHEMA

AXES = ("identification", "verification", "policy", "value")

_AXIS_FIELDS = {
    "identification": ("source", "proposition", "created_at"),
    "verification": ("verdict", "evidence_kind", "fidelity_state",
                     "freshness_state", "reproduction_state"),
    "policy": ("review_state", "community_state"),
    "value": ("novelty_state",),
}

_KNOWN = {
    "review_state": {"unreviewed", "under_review", "reviewed", "contested"},
    "evidence_kind": {"benchmark", "case_study", "reproduction", "survey"},
    "community_state": {"unreviewed", "discussed", "adopted", "rejected"},
    "fidelity_state": {"faithful", "partial", "unverified"},
    "freshness_state": {"fresh", "aging", "stale"},
    "reproduction_state": {"unattempted", "attempted", "reproduced",
                           "failed_reproduction"},
    "verdict": {"supported", "refuted", "mixed", "unverified"},
    "novelty_state": {"novel", "known", "NOT_FOUND_IN_CORPUS"},
}


def project_frontier_axes(
    *,
    claim: dict,
    journey_ref: str,
    event_head_sha256: str,
) -> dict:
    if claim.get("schema") != CLAIM_SCHEMA:
        raise ValueError("the claim is not an admitted frontier claim")
    if claim.get("journey_ref") != journey_ref:
        raise ValueError("the claim names a different journey")
    if (not isinstance(event_head_sha256, str)
            or len(event_head_sha256) != 64):
        raise ValueError("event head is not a sha256")
    axes = []
    for axis in AXES:
        fields: dict = {}
        raw_unrecognized: list[str] = []
        for field in _AXIS_FIELDS[axis]:
            if field in ("source", "proposition", "created_at"):
                fields[field] = claim["identification"][field]
                continue
            if field in claim:
                value = claim[field]
                fields[field] = value
                if (isinstance(value, str)
                        and value not in _KNOWN.get(field, set())
                        and value != "NOT_FOUND_IN_CORPUS"
                        and field != "novelty_state"):
                    raw_unrecognized.append(value)
                elif (field == "novelty_state"
                      and isinstance(value, str)
                      and value not in _KNOWN[field]):
                    raw_unrecognized.append(value)
        axes.append({
            "axis": axis,
            "fields": fields,
            "raw_unrecognized": sorted(set(raw_unrecognized)),
            "fields_sha256": canonical_sha256(fields),
        })
    return {
        "schema": "flywheel.frontier-axes/v1",
        "claim_id": claim["claim_id"],
        "journey_ref": journey_ref,
        "event_head_sha256": event_head_sha256,
        "claim_sha256": claim["claim_sha256"],
        "axes": axes,
        "does_not_prove": (
            "independent axes are observations, not a composite judgment; "
            "no score exists and none may be derived"),
    }


def append_frontier_axis_event(
    *,
    owner_ref: str,
    journey_ref: str,
    expected_event_head: str,
    client_request_id: str,
    grant_ref: str,
    claim_id: str,
    axis: str,
    patch: dict,
) -> dict:
    if axis not in _AXIS_FIELDS:
        raise ValueError("unknown axis; cross-axis mutation is refused")
    if axis == "identification":
        raise ValueError("identification is immutable after admission")
    for field in patch:
        if field not in _AXIS_FIELDS[axis]:
            raise ValueError("cross-axis mutation is refused")
    if field_is_inferred_novelty(axis, patch):
        raise ValueError(
            "novelty is never inferred; NOT_FOUND_IN_CORPUS stays literal")
    if (not owner_ref.startswith("owner_")
            or not journey_ref.startswith("jrn_")
            or len(expected_event_head) != 64
            or not client_request_id
            or not grant_ref.startswith("gnt_")
            or not claim_id.startswith("clm_")):
        raise ValueError("the axis event lacks a valid binding")
    # Delegation point: one typed CAS command carries this patch. This
    # module never retrieves sources and never executes a checker.
    return {
        "schema": "flywheel.frontier-axis-event/v1",
        "axis": axis,
        "patch": patch,
        "claim_id": claim_id,
        "journey_ref": journey_ref,
        "expected_event_head": expected_event_head,
        "grant_ref": grant_ref,
        "client_request_id": client_request_id,
        "owner_ref": owner_ref,
    }


def field_is_inferred_novelty(axis: str, patch: dict) -> bool:
    if axis != "value":
        return False
    novelty = patch.get("novelty_state")
    return isinstance(novelty, str) and novelty not in _KNOWN["novelty_state"]
