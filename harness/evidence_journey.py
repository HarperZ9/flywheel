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
_ACTION_FIELDS = frozenset(("action_id", "kind", "description", "basis_refs"))
_ACTION_KINDS = frozenset(("inspect", "rerun", "collect", "escalate", "repair",
                           "rollback", "recheck", "export"))
_MAX_DEPTH = 64
def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)
def _text(value: object, field: str) -> str:
    _require(type(value) is str and bool(value.strip()), f"{field} must be a non-empty string")
    return value
def _time(value: object, field: str) -> datetime:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None, f"{field} must include a timezone")
    return parsed
def _string_list(value: object, field: str, *, nonempty: bool = False) -> list[str]:
    _require(type(value) is list and not (nonempty and not value),
             f"{field} must be a{' non-empty' if nonempty else ''} list")
    for item in value:
        _text(item, field)
    _require(len(value) == len(set(value)), f"{field} must not contain duplicates")
    return value
def _require_bounded_depth(value: object) -> None:
    active: set[int] = set()
    stack = [(value, 0, False)]
    while stack:
        item, depth, leaving = stack.pop()
        if type(item) not in (dict, list):
            continue
        identity = id(item)
        if leaving:
            active.remove(identity)
            continue
        _require(depth <= _MAX_DEPTH, "journey exceeds structural depth limit")
        _require(identity not in active, "journey must not contain a cycle")
        active.add(identity)
        stack.append((item, depth, True))
        children = item.values() if type(item) is dict else item
        stack.extend((child, depth + 1, False) for child in reversed(list(children)))
def _validate_metric(metric: object, denominators: dict[str, object]) -> None:
    _require(type(metric) is dict, "metric must be an object")
    _text(metric.get("metric_id"), "metric_id")
    _require("value" in metric, "metric value is required")
    value = metric["value"]
    if value is None:
        _text(metric.get("reason"), "reason")
    else:
        _require(type(value) in (int, float), "metric value must be numeric or null")
    denominator = metric.get("denominator")
    _require(type(denominator) is int and denominator >= 0,
             "denominator must be a non-negative integer")
    if "numerator" in metric:
        numerator = metric["numerator"]
        _require(type(numerator) is int and 0 <= numerator <= denominator,
                 "numerator is inconsistent with denominator")
        _require(value is None or (denominator > 0 and value == numerator / denominator),
                 "metric value is inconsistent with denominator")
    else:
        _require(value is None or denominator > 0,
                 "non-null metric requires a nonzero denominator")
    if "denominator_id" in metric:
        key = _text(metric["denominator_id"], "denominator_id")
        _require(key not in denominators or denominators[key] == denominator,
                 "denominator_id changed denominator")
        denominators[key] = denominator
def _validate_attestation(attestation: object, at: datetime) -> None:
    _require(type(attestation) is dict, "attestation must be an object")
    for field in ("subject", "role"):
        _text(attestation.get(field), field)
    for field in ("scope", "basis"):
        value = attestation.get(field)
        _text(value, field) if type(value) is str else _string_list(value, field, nonempty=True)
    issued = _time(attestation.get("issued_at"), "issued_at")
    expires = _time(attestation.get("expires_at"), "expires_at")
    _require(expires > issued, "expires_at must be after issued_at")
    state = attestation.get("signature_state")
    _require(state in ("signed", "unsigned"), "signature_state must be signed or unsigned")
    signature = attestation.get("signature")
    if state == "signed":
        _text(signature, "signature")
    elif signature is not None:
        raise ValueError("unsigned attestation cannot carry a signature")
    for field in ("requires_signature", "requires_active"):
        _require(field not in attestation or type(attestation[field]) is bool,
                 f"{field} must be a boolean")
    _require(attestation.get("requires_signature") is not True or state == "signed",
             "signed attestation is required")
    _require(attestation.get("requires_active") is not True or expires > at,
             "attestation is expired")
    _require(issued <= at, "attestation was issued after its event")
def _validate_claim(claim: object) -> tuple[str, list[str]]:
    _require(type(claim) is dict, "claim must be an object")
    claim_id = _text(claim.get("claim_id"), "claim_id")
    _text(claim.get("statement"), "statement")
    dependencies = _string_list(claim.get("depends_on"), "depends_on")
    verdict = claim.get("verdict")
    _require(verdict in VERDICTS, "claim verdict must use the four-way vocabulary")
    if verdict in ("UNDECIDED", "UNVERIFIABLE"):
        _text(claim.get("reason"), "reason")
    _string_list(claim.get("receipt_refs", []), "receipt_refs")
    return claim_id, dependencies
def _validate_claim_graph(claims: dict[str, dict]) -> None:
    dependencies = {claim_id: claim["depends_on"] for claim_id, claim in claims.items()}
    for claim_id, refs in dependencies.items():
        for ref in refs:
            _require(ref in claims, f"claim {claim_id} has missing dependency {ref}")
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
    _require(type(journey) is dict, "journey must be an object")
    _require_bounded_depth(journey)
    canonical_sha256(journey)
    _require(journey.get("schema") == SCHEMA, f"journey schema must be {SCHEMA}")
    _text(journey.get("journey_id"), "journey_id")
    _text(journey.get("goal"), "goal")
    created = _time(journey.get("created_at"), "created_at")
    _require(type(journey.get("intake")) is dict, "intake must be an object")
    events = journey.get("events")
    _require(type(events) is list, "events must be a list")
    claims: dict[str, dict] = {}
    actions: list[dict] = []
    action_definitions: dict[str, dict] = {}
    denominators: dict[str, object] = {}
    available_basis = _receipt_refs(journey["intake"])
    prior_hash = None
    prior_time = created
    for index, event in enumerate(events, start=1):
        _require(type(event) is dict, "event must be an object")
        expected_stage = STAGES[index] if index < len(STAGES) else None
        _require(event.get("stage") == expected_stage, "invalid journey stage transition")
        occurred = _time(event.get("occurred_at"), "occurred_at")
        _require(occurred >= prior_time, "event timestamps must be monotonic")
        _require(event.get("prior_event_sha256") == prior_hash, "prior event hash mismatch")
        content = {key: value for key, value in event.items() if key != "event_sha256"}
        event_hash = canonical_sha256(content)
        _require(event.get("event_sha256") == event_hash, "event hash mismatch")
        for field in ("metrics", "attestations", "claims", "next_actions"):
            _require(type(event.get(field, [])) is list, f"{field} must be a list")
        if "receipt_refs" in event:
            available_basis.update(_string_list(event["receipt_refs"], "receipt_refs"))
        for metric in event.get("metrics", []):
            _validate_metric(metric, denominators)
            available_basis.add(metric["metric_id"])
            available_basis.update(_receipt_refs(metric))
        for attestation in event.get("attestations", []):
            _validate_attestation(attestation, occurred)
            available_basis.update(_receipt_refs(attestation))
        seen: set[str] = set()
        for claim in event.get("claims", []):
            claim_id, dependencies = _validate_claim(claim)
            _require(claim_id not in seen, "duplicate claim_id in one event")
            if claim_id in claims:
                _require(claims[claim_id]["depends_on"] == dependencies,
                         "claim dependencies are immutable")
                _require(claims[claim_id]["statement"] == claim["statement"],
                         "claim statement is immutable")
            seen.add(claim_id)
            claims[claim_id] = deepcopy(claim)
            available_basis.add(claim_id)
            available_basis.update(claim["receipt_refs"])
        for action in event.get("next_actions", []):
            _require(type(action) is dict, "next action must be an object")
            missing = _ACTION_FIELDS - action.keys()
            unknown = action.keys() - _ACTION_FIELDS
            _require(not missing, f"missing next action fields: {', '.join(sorted(missing))}")
            _require(not unknown, f"unknown next action fields: {', '.join(sorted(unknown))}")
            action_id = _text(action["action_id"], "action_id")
            _require(action["kind"] in _ACTION_KINDS, "next action kind is unknown")
            _text(action["description"], "description")
            basis_refs = _string_list(action.get("basis_refs"), "basis_refs", nonempty=True)
            _require(action_id not in basis_refs, "next action cannot cite itself as basis")
            unresolved = [ref for ref in basis_refs if ref not in available_basis]
            _require(not unresolved, "next action has unresolved basis_ref " +
                     (unresolved[0] if unresolved else ""))
            _require(action_id not in action_definitions or action_definitions[action_id] == action,
                     "next action fields are immutable")
            action_definitions[action_id] = deepcopy(action)
            actions.append(deepcopy(action))
        _validate_claim_graph(claims)
        prior_hash, prior_time = event_hash, occurred
    expected_stage = STAGES[len(events)] if len(events) < len(STAGES) else None
    _require(expected_stage is not None and journey.get("stage") == expected_stage,
             "journey stage does not match its events")
    _require(journey.get("event_head_sha256") == prior_hash, "event head hash mismatch")
    return claims, _receipt_refs(journey), actions
def new_journey(*, journey_id: str, goal: str, intake: dict,
                created_at: str) -> dict:
    """Create an intake-stage journey without retaining caller-owned objects."""
    _require_bounded_depth(intake)
    journey = {
        "schema": SCHEMA, "journey_id": _text(journey_id, "journey_id"),
        "goal": _text(goal, "goal"), "created_at": created_at,
        "intake": deepcopy(intake), "stage": "intake", "events": [],
        "event_head_sha256": None,
    }
    _validate(journey)
    return journey
def append_event(journey: dict, event: dict) -> dict:
    """Return a new journey with one validated, hash-bound stage event."""
    _validate(journey)
    _require(type(event) is dict, "event must be an object")
    _require_bounded_depth(event)
    canonical_sha256(event)
    _require(not _PROTECTED_EVENT_KEYS.intersection(event),
             "event hash fields are assigned by append_event")
    next_index = STAGES.index(journey["stage"]) + 1
    _require(next_index < len(STAGES) and event.get("stage") == STAGES[next_index],
             "invalid journey stage transition")
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
    _require(type(lens) is str and lens.lower() in LENSES,
             "lens must be Rescue, Diagnose, or Verify")
    claims, receipt_refs, actions = _validate(journey)
    name = lens.lower()
    details = {
        "claims": [claims[key] for key in sorted(claims)],
        "next_actions": actions, "events": deepcopy(journey["events"]),
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
    except (TypeError, ValueError, RecursionError) as exc:
        return {"verdict": "FAIL", "reason": str(exc)}
    return {
        "verdict": "PASS",
        "journey_id": journey["journey_id"],
        "stage": journey["stage"],
        "event_head_sha256": journey["event_head_sha256"],
        "claim_ids": sorted(claims),
        "receipt_refs": sorted(receipt_refs),
    }
