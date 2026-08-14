"""Stdlib-only types and validation for durable evidence Journey v2 events."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re

from .evidence_json import canonical_sha256

EVENT_SCHEMA = "flywheel.evidence-journey-event/v2"
PROJECTION_SCHEMA = "flywheel.evidence-journey-projection/v2"
EVENT_KEYS = frozenset((
    "schema", "journey_ref", "sequence", "event_type", "occurred_at", "actor_id",
    "request_sha256", "payload", "prior_event_sha256", "event_sha256",
))
STAGES = ("intake", "decomposed", "preflight", "running", "concluded", "exported")
OPERATIONAL_EVENT_TYPES = frozenset((
    "record_fact", "record_claim", "record_next_action", "record_receipt",
    "check_requested", "check_blocked", "check_started", "check_completed",
    "check_failed", "check_cancelled", "cancel_requested",
))
EVENT_TYPES = frozenset(STAGES) | OPERATIONAL_EVENT_TYPES
VERDICTS = frozenset(("PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"))
RECEIPT_STATES = frozenset((
    "missing", "present_unchecked", "MATCH", "DRIFT", "TAMPERED", "UNVERIFIABLE",
))
JOURNEY_REF_PATTERN = re.compile(r"jrn_[0-9a-f]{32}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_text(value: object, field: str) -> str:
    require(type(value) is str and bool(value.strip()), f"{field} must be a non-empty string")
    return value


def validate_journey_ref(value: object) -> str:
    require(type(value) is str and JOURNEY_REF_PATTERN.fullmatch(value) is not None,
            "journey_ref must match jrn_ plus 32 lowercase hex characters")
    return value


def _validate_time(value: object, field: str) -> None:
    text = require_text(value, field)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    require(parsed.tzinfo is not None, f"{field} must include a timezone")


def _validate_sha256(value: object, field: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    require(type(value) is str and SHA256_PATTERN.fullmatch(value) is not None,
            f"{field} must be 64 lowercase hex characters")


def event_sha256(event: dict) -> str:
    """Hash an event's sealed content, excluding its self-referential digest."""
    return canonical_sha256({key: value for key, value in event.items() if key != "event_sha256"})


def validate_event(event: object) -> dict:
    """Fail closed unless one event is exact, canonical, and self-hash-bound."""
    require(type(event) is dict and set(event) == EVENT_KEYS, "event must have the exact v2 fields")
    require(event.get("schema") == EVENT_SCHEMA, "event schema is not v2")
    validate_journey_ref(event.get("journey_ref"))
    require(type(event.get("sequence")) is int and event["sequence"] >= 0,
            "sequence must be a non-negative integer")
    require(event.get("event_type") in EVENT_TYPES, "event_type is not in the v2 enum")
    _validate_time(event.get("occurred_at"), "occurred_at")
    require_text(event.get("actor_id"), "actor_id")
    _validate_sha256(event.get("request_sha256"), "request_sha256")
    require(type(event.get("payload")) is dict, "payload must be an object")
    _validate_sha256(event.get("prior_event_sha256"), "prior_event_sha256", nullable=True)
    _validate_sha256(event.get("event_sha256"), "event_sha256")
    require(event["event_sha256"] == event_sha256(event), "event_sha256 does not match canonical event")
    return deepcopy(event)


def build_event(*, journey_ref: str, sequence: int, event_type: str, occurred_at: str,
                actor_id: str, request_sha256: str, payload: dict,
                prior_event_sha256: str | None) -> dict:
    """Build one canonical immutable event for trusted mutation services."""
    event = {
        "schema": EVENT_SCHEMA, "journey_ref": journey_ref, "sequence": sequence,
        "event_type": event_type, "occurred_at": occurred_at, "actor_id": actor_id,
        "request_sha256": request_sha256, "payload": deepcopy(payload),
        "prior_event_sha256": prior_event_sha256,
    }
    event["event_sha256"] = event_sha256(event)
    return validate_event(event)
