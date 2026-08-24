"""incident_case.py -- the admitted-facts input to the Incident Compiler.

A case binds one journey head to public-safe source facts and one
failure statement. Secret-shaped keys and host paths are refused before
anything is stored; the case is deterministic and hash-bound so the
later proposal cites an exact input.
"""
from __future__ import annotations

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.incident-case/v1"
_FIELDS = {"case_id", "journey_ref", "event_head_sha256", "source_refs",
           "failure", "created_at"}
_SECRET_KEY = ("api_key", "token", "secret", "password", "credential",
               "authorization", "cookie", "private_key")
_REF = ("fact_", "claim_", "rcpt_", "op_", "jrn_")


def _public(value: object, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("incident metadata nests too deeply")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("incident metadata keys must be text")
            lowered = key.lower()
            if any(secret in lowered for secret in _SECRET_KEY):
                raise ValueError("incident metadata must not carry secrets")
            if lowered in ("log_path", "path", "file", "host_path"):
                raise ValueError("incident metadata must not carry paths")
            _public(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _public(child, depth + 1)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("incident metadata must be plain JSON")


def _ref(value: object) -> bool:
    return (isinstance(value, str) and len(value) >= 8
            and value.startswith(_REF))


def new_incident_case(
    *,
    case_id: str,
    journey_ref: str,
    event_head_sha256: str,
    source_refs: list[dict],
    failure: dict,
    created_at: str,
) -> dict:
    if not isinstance(case_id, str) or not case_id.startswith("case_"):
        raise ValueError("case id is not a case ref")
    if not journey_ref.startswith("jrn_"):
        raise ValueError("journey ref is not a journey ref")
    if (not isinstance(event_head_sha256, str)
            or len(event_head_sha256) != 64):
        raise ValueError("event head is not a sha256")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError("created_at is required")
    if (not isinstance(source_refs, list) or not source_refs
            or any(not isinstance(ref, dict) or not _ref(ref.get("fact_id"))
                   for ref in source_refs)):
        raise ValueError("source refs must name admitted facts")
    if not isinstance(failure, dict) or not failure.get("summary"):
        raise ValueError("failure must carry a summary statement")
    _public(failure)
    case = {
        "schema": SCHEMA,
        "case_id": case_id,
        "journey_ref": journey_ref,
        "event_head_sha256": event_head_sha256,
        "source_refs": sorted(
            source_refs, key=lambda ref: canonical_sha256(ref)),
        "failure": failure,
        "created_at": created_at,
    }
    case["case_sha256"] = canonical_sha256(
        {k: v for k, v in case.items() if k != "case_sha256"})
    return case
