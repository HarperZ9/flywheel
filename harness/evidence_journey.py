"""Deterministic evidence-journey events and read-only projections."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from harness.evidence_json import canonical_sha256

SCHEMA = "flywheel.evidence-journey/v1"
STAGES = ("intake", "decomposed", "preflight", "running", "concluded", "exported")
VERDICTS = frozenset(("PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"))
LENSES = frozenset(("rescue", "diagnose", "verify"))
_PROTECTED_EVENT_KEYS = frozenset(("prior_event_sha256", "event_sha256"))
_ACTION_MUTATION_KEYS = frozenset(("verdict", "claim_verdict", "claims", "claim_updates"))
def _text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value
def _time(value: object, field: str) -> datetime:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed
def _string_list(value: object, field: str, *, nonempty: bool = False) -> list[str]:
    if type(value) is not list or (nonempty and not value):
        raise ValueError(f"{field} must be a{' non-empty' if nonempty else ''} list")
    for item in value:
        _text(item, field)
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    return value
def _contains_key(value: object, forbidden: frozenset[str]) -> bool:
    if type(value) is dict:
        return any(key in forbidden or _contains_key(item, forbidden)
                   for key, item in value.items())
    if type(value) is list:
        return any(_contains_key(item, forbidden) for item in value)
    return False
def _validate_metric(metric: object, denominators: dict[str, object]) -> None:
    if type(metric) is not dict:
        raise ValueError("metric must be an object")
    _text(metric.get("metric_id"), "metric_id")
    if "value" not in metric:
        raise ValueError("metric value is required")
    value = metric["value"]
    if value is None:
        _text(metric.get("reason"), "reason")
    elif type(value) not in (int, float):
        raise ValueError("metric value must be numeric or null")
    denominator = metric.get("denominator")
    if type(denominator) is not int or denominator < 0:
        raise ValueError("denominator must be a non-negative integer")
    if "numerator" in metric:
        numerator = metric["numerator"]
        if type(numerator) is not int or numerator < 0 or numerator > denominator:
            raise ValueError("numerator is inconsistent with denominator")
        if value is not None and (denominator == 0 or value != numerator / denominator):
            raise ValueError("metric value is inconsistent with denominator")
    elif value is not None and denominator == 0:
        raise ValueError("non-null metric requires a nonzero denominator")
    if "denominator_id" in metric:
        key = _text(metric["denominator_id"], "denominator_id")
        if key in denominators and denominators[key] != denominator:
            raise ValueError("denominator_id changed denominator")
        denominators[key] = denominator
def _validate_attestation(attestation: object, at: datetime) -> None:
    if type(attestation) is not dict:
        raise ValueError("attestation must be an object")
    for field in ("subject", "role"):
        _text(attestation.get(field), field)
    for field in ("scope", "basis"):
        value = attestation.get(field)
        _text(value, field) if type(value) is str else _string_list(value, field, nonempty=True)
    issued = _time(attestation.get("issued_at"), "issued_at")
    expires = _time(attestation.get("expires_at"), "expires_at")
    if expires <= issued:
        raise ValueError("expires_at must be after issued_at")
    state = attestation.get("signature_state")
    if state not in ("signed", "unsigned"):
        raise ValueError("signature_state must be signed or unsigned")
    signature = attestation.get("signature")
    if state == "signed":
        _text(signature, "signature")
    elif signature is not None:
        raise ValueError("unsigned attestation cannot carry a signature")
    for field in ("requires_signature", "requires_active"):
        if field in attestation and type(attestation[field]) is not bool:
            raise ValueError(f"{field} must be a boolean")
    if attestation.get("requires_signature") is True and state != "signed":
        raise ValueError("signed attestation is required")
    if attestation.get("requires_active") is True and expires <= at:
        raise ValueError("attestation is expired")
    if issued > at:
        raise ValueError("attestation was issued after its event")
def _validate_claim(claim: object) -> tuple[str, list[str]]:
    if type(claim) is not dict:
        raise ValueError("claim must be an object")
    claim_id = _text(claim.get("claim_id"), "claim_id")
    _text(claim.get("statement"), "statement")
    dependencies = _string_list(claim.get("depends_on"), "depends_on")
    verdict = claim.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError("claim verdict must use the four-way vocabulary")
    if verdict in ("UNDECIDED", "UNVERIFIABLE"):
        _text(claim.get("reason"), "reason")
    _string_list(claim.get("receipt_refs", []), "receipt_refs")
    return claim_id, dependencies
def _validate_claim_graph(claims: dict[str, dict]) -> None:
    dependencies = {claim_id: claim["depends_on"] for claim_id, claim in claims.items()}
    for claim_id, refs in dependencies.items():
        missing = [ref for ref in refs if ref not in claims]
        if missing:
            raise ValueError(f"claim {claim_id} has missing dependency {missing[0]}")
    state: dict[str, int] = {}
    for root in dependencies:
        stack = [(root, False)]
        while stack:
            claim_id, expanded = stack.pop()
            if expanded:
                state[claim_id] = 2
                continue
            if state.get(claim_id) == 2:
                continue
            if state.get(claim_id) == 1:
                raise ValueError("claim dependency cycle")
            state[claim_id] = 1
            stack.append((claim_id, True))
            for dependency in reversed(dependencies[claim_id]):
                if state.get(dependency) == 1:
                    raise ValueError("claim dependency cycle")
                if state.get(dependency) != 2:
                    stack.append((dependency, False))
def _receipt_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if type(value) is dict:
        for key, item in value.items():
            if key == "receipt_refs":
                refs.update(_string_list(item, "receipt_refs"))
            else:
                refs.update(_receipt_refs(item))
    elif type(value) is list:
        for item in value:
            refs.update(_receipt_refs(item))
    return refs
def _validate(journey: object) -> tuple[dict[str, dict], set[str], list[dict]]:
    if type(journey) is not dict:
        raise ValueError("journey must be an object")
    canonical_sha256(journey)
    if journey.get("schema") != SCHEMA:
        raise ValueError(f"journey schema must be {SCHEMA}")
    _text(journey.get("journey_id"), "journey_id")
    _text(journey.get("goal"), "goal")
    created = _time(journey.get("created_at"), "created_at")
    if type(journey.get("intake")) is not dict:
        raise ValueError("intake must be an object")
    events = journey.get("events")
    if type(events) is not list:
        raise ValueError("events must be a list")
    claims: dict[str, dict] = {}
    actions: list[dict] = []
    denominators: dict[str, object] = {}
    prior_hash = None
    prior_time = created
    for index, event in enumerate(events, start=1):
        if type(event) is not dict:
            raise ValueError("event must be an object")
        expected_stage = STAGES[index] if index < len(STAGES) else None
        if event.get("stage") != expected_stage:
            raise ValueError("invalid journey stage transition")
        occurred = _time(event.get("occurred_at"), "occurred_at")
        if occurred < prior_time:
            raise ValueError("event timestamps must be monotonic")
        if event.get("prior_event_sha256") != prior_hash:
            raise ValueError("prior event hash mismatch")
        content = {key: value for key, value in event.items() if key != "event_sha256"}
        event_hash = canonical_sha256(content)
        if event.get("event_sha256") != event_hash:
            raise ValueError("event hash mismatch")
        for field in ("metrics", "attestations", "claims", "next_actions"):
            if type(event.get(field, [])) is not list:
                raise ValueError(f"{field} must be a list")
        for metric in event.get("metrics", []):
            _validate_metric(metric, denominators)
        for attestation in event.get("attestations", []):
            _validate_attestation(attestation, occurred)
        seen: set[str] = set()
        for claim in event.get("claims", []):
            claim_id, dependencies = _validate_claim(claim)
            if claim_id in seen:
                raise ValueError("duplicate claim_id in one event")
            if claim_id in claims:
                if claims[claim_id]["depends_on"] != dependencies:
                    raise ValueError("claim dependencies are immutable")
                if claims[claim_id]["statement"] != claim["statement"]:
                    raise ValueError("claim statement is immutable")
            seen.add(claim_id)
            claims[claim_id] = deepcopy(claim)
        for action in event.get("next_actions", []):
            if type(action) is not dict:
                raise ValueError("next action must be an object")
            _string_list(action.get("basis_refs"), "basis_refs", nonempty=True)
            if _contains_key(action, _ACTION_MUTATION_KEYS):
                raise ValueError("next action cannot mutate a claim verdict")
            actions.append(deepcopy(action))
        _validate_claim_graph(claims)
        prior_hash, prior_time = event_hash, occurred
    expected_stage = STAGES[len(events)] if len(events) < len(STAGES) else None
    if expected_stage is None or journey.get("stage") != expected_stage:
        raise ValueError("journey stage does not match its events")
    if journey.get("event_head_sha256") != prior_hash:
        raise ValueError("event head hash mismatch")
    return claims, _receipt_refs(journey), actions
def new_journey(*, journey_id: str, goal: str, intake: dict,
                created_at: str) -> dict:
    """Create an intake-stage journey without retaining caller-owned objects."""
    journey = {
        "schema": SCHEMA,
        "journey_id": _text(journey_id, "journey_id"),
        "goal": _text(goal, "goal"),
        "created_at": created_at,
        "intake": deepcopy(intake),
        "stage": "intake",
        "events": [],
        "event_head_sha256": None,
    }
    _validate(journey)
    return journey
def append_event(journey: dict, event: dict) -> dict:
    """Return a new journey with one validated, hash-bound stage event."""
    _validate(journey)
    if type(event) is not dict:
        raise ValueError("event must be an object")
    canonical_sha256(event)
    if _PROTECTED_EVENT_KEYS.intersection(event):
        raise ValueError("event hash fields are assigned by append_event")
    next_index = STAGES.index(journey["stage"]) + 1
    if next_index >= len(STAGES) or event.get("stage") != STAGES[next_index]:
        raise ValueError("invalid journey stage transition")
    result = deepcopy(journey)
    stored = deepcopy(event)
    stored["prior_event_sha256"] = result["event_head_sha256"]
    stored["event_sha256"] = canonical_sha256(stored)
    result["events"].append(stored)
    result["stage"] = stored["stage"]
    result["event_head_sha256"] = stored["event_sha256"]
    _validate(result)
    return result
def project_journey(journey: dict, *, lens: str) -> dict:
    """Project one validated journey without changing server-owned evidence facts."""
    if type(lens) is not str or lens.lower() not in LENSES:
        raise ValueError("lens must be Rescue, Diagnose, or Verify")
    claims, receipt_refs, actions = _validate(journey)
    name = lens.lower()
    details = {
        "claims": [claims[key] for key in sorted(claims)],
        "next_actions": actions,
        "events": deepcopy(journey["events"]),
    }
    order = {
        "rescue": ("next_actions", "claims", "events"),
        "diagnose": ("claims", "events", "next_actions"),
        "verify": ("events", "claims", "next_actions"),
    }[name]
    return {
        "schema": SCHEMA,
        "lens": name.title(),
        "journey_id": journey["journey_id"],
        "stage": journey["stage"],
        "event_head_sha256": journey["event_head_sha256"],
        "claim_ids": sorted(claims),
        "verdicts": {key: claims[key]["verdict"] for key in sorted(claims)},
        "receipt_refs": sorted(receipt_refs),
        "detail": {key: details[key] for key in order},
    }
def verify_journey(journey: dict) -> dict:
    """Return a fail-closed structural and hash-chain verdict."""
    try:
        claims, receipt_refs, _ = _validate(journey)
    except (TypeError, ValueError) as exc:
        return {"verdict": "FAIL", "reason": str(exc)}
    return {
        "verdict": "PASS",
        "journey_id": journey["journey_id"],
        "stage": journey["stage"],
        "event_head_sha256": journey["event_head_sha256"],
        "claim_ids": sorted(claims),
        "receipt_refs": sorted(receipt_refs),
    }
