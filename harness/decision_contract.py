"""Bounded native decision proposal contract.

This module validates declared choice requests and model-like proposal JSON. It
does not call providers, execute tools, authorize actions, or certify semantic
correctness.
"""
from __future__ import annotations

import hashlib
import re

from .evidence_json import canonical_sha256, strict_load_json

REQUEST_SCHEMA = "flywheel.decision-request/v1"
RESULT_SCHEMA = "flywheel.decision-result/v1"
DOES_NOT_PROVE = (
    "Validates request/proposal shape, declared choice eligibility, and cited "
    "reference membership only; does not prove semantic correctness, "
    "authorization, execution, model calibration, or competitive performance."
)
REQUEST_KEYS = {
    "schema", "decision_ref", "state", "choices",
    "eligible_choice_ids", "evidence_refs",
}
CHOICE_KEYS = {"id", "description"}
PROPOSAL_KEYS = {"choice_id", "evidence_refs"}
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MAX_STATE_CHARS = 8192
MAX_DESCRIPTION_CHARS = 2048
MAX_CHOICES = 50
MAX_EVIDENCE_REFS = 100
MAX_RESPONSE_BYTES = 4096


class DecisionContractError(ValueError):
    """A fixed request-contract failure."""


def _fail() -> None:
    raise DecisionContractError("INVALID_DECISION_REQUEST")


def _id(value: object) -> str:
    if type(value) is not str or ID_PATTERN.fullmatch(value) is None:
        _fail()
    return value


def _text(value: object, limit: int) -> str:
    if type(value) is not str or not value or len(value) > limit:
        _fail()
    for ch in value:
        if ord(ch) < 32 and ch not in "\n\r\t":
            _fail()
    return value


def _unique_ids(values: object, allowed: set[str] | None = None,
                limit: int = MAX_EVIDENCE_REFS) -> list[str]:
    if type(values) is not list or len(values) > limit:
        _fail()
    out, seen = [], set()
    for item in values:
        name = _id(item)
        if name in seen or (allowed is not None and name not in allowed):
            _fail()
        seen.add(name)
        out.append(name)
    return out


def validate_request(payload: dict) -> dict:
    """Return an independent validated snapshot of a decision request."""
    if type(payload) is not dict or set(payload) != REQUEST_KEYS:
        _fail()
    if payload.get("schema") != REQUEST_SCHEMA:
        _fail()
    choices = payload["choices"]
    if type(choices) is not list or not 1 <= len(choices) <= MAX_CHOICES:
        _fail()
    frozen_choices, choice_ids = [], set()
    for choice in choices:
        if type(choice) is not dict or set(choice) != CHOICE_KEYS:
            _fail()
        cid = _id(choice["id"])
        if cid in choice_ids:
            _fail()
        choice_ids.add(cid)
        frozen_choices.append({
            "id": cid,
            "description": _text(
                choice["description"], MAX_DESCRIPTION_CHARS),
        })
    snapshot = {
        "schema": REQUEST_SCHEMA,
        "decision_ref": _id(payload["decision_ref"]),
        "state": _text(payload["state"], MAX_STATE_CHARS),
        "choices": frozen_choices,
        "eligible_choice_ids": _unique_ids(
            payload["eligible_choice_ids"], choice_ids, MAX_CHOICES),
        "evidence_refs": _unique_ids(payload["evidence_refs"]),
    }
    try:
        canonical_sha256(snapshot)
    except ValueError:
        _fail()
    return snapshot


def _response_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_response(response: object) -> tuple[str | None, str | None]:
    if type(response) is not str:
        return None, "invalid_shape"
    if len(response) > MAX_RESPONSE_BYTES:
        return None, "response_oversize"
    raw = response.encode("utf-8", "surrogatepass")
    if len(raw) > MAX_RESPONSE_BYTES:
        return None, "response_oversize"
    return _response_sha256(raw), None


def _result(request: dict, response_sha256: str | None, scorer_ref: str, reason: str,
            *, choice_id: str | None = None,
            evidence_refs: list[str] | None = None) -> dict:
    selected = reason == "selected"
    return {
        "schema": RESULT_SCHEMA,
        "disposition": "selected" if selected else "abstained",
        "choice_id": choice_id if selected else None,
        "reason_code": reason,
        "evidence_refs": list(evidence_refs or []) if selected or reason == "abstain" else [],
        "request_sha256": canonical_sha256(request),
        "response_sha256": response_sha256,
        "scorer_ref": (scorer_ref if type(scorer_ref) is str
                       and ID_PATTERN.fullmatch(scorer_ref) else ""),
        "does_not_prove": DOES_NOT_PROVE,
    }


def _parse_response(response: object) -> tuple[dict | None, str | None]:
    if type(response) is not str:
        return None, "invalid_shape"
    try:
        value = strict_load_json(
            response.encode("utf-8", "surrogatepass"),
            max_bytes=MAX_RESPONSE_BYTES, max_depth=4)
    except (ValueError, RecursionError) as exc:
        text = str(exc)
        if "duplicate JSON key" in text:
            return None, "duplicate_key"
        return None, "malformed_json"
    if type(value) is not dict or set(value) != PROPOSAL_KEYS:
        return None, "invalid_shape"
    refs = value.get("evidence_refs")
    if type(refs) is not list:
        return None, "invalid_shape"
    seen_refs = set()
    for ref in refs:
        if type(ref) is not str or ref in seen_refs:
            return None, "invalid_shape"
        seen_refs.add(ref)
    choice = value.get("choice_id")
    if choice is not None and type(choice) is not str:
        return None, "invalid_shape"
    return value, None


def evaluate_proposal(request: dict, response: str, *,
                      scorer_ref: str) -> dict:
    """Validate one proposal against a request and return a fixed result."""
    snapshot = validate_request(request)
    response_sha256, response_error = _check_response(response)
    if response_error is not None:
        return _result(snapshot, response_sha256, scorer_ref, response_error)
    if type(scorer_ref) is not str or ID_PATTERN.fullmatch(scorer_ref) is None:
        return _result(snapshot, response_sha256, "", "invalid_scorer_ref")
    if not snapshot["eligible_choice_ids"]:
        return _result(snapshot, response_sha256, scorer_ref, "empty_eligibility")
    proposal, reason = _parse_response(response)
    if proposal is None:
        return _result(snapshot, response_sha256, scorer_ref, reason or "invalid_shape")
    supplied_refs = set(snapshot["evidence_refs"])
    if any(ref not in supplied_refs for ref in proposal["evidence_refs"]):
        return _result(snapshot, response_sha256, scorer_ref, "invented_evidence_ref")
    choice = proposal["choice_id"]
    if choice is None:
        return _result(
            snapshot, response_sha256, scorer_ref, "abstain",
            evidence_refs=list(proposal["evidence_refs"]))
    declared = {item["id"] for item in snapshot["choices"]}
    if choice not in declared:
        return _result(snapshot, response_sha256, scorer_ref, "unknown_choice")
    if choice not in set(snapshot["eligible_choice_ids"]):
        return _result(snapshot, response_sha256, scorer_ref, "ineligible_choice")
    return _result(
        snapshot, response_sha256, scorer_ref, "selected", choice_id=choice,
        evidence_refs=list(proposal["evidence_refs"]))
