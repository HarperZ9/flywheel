"""Pure event reduction and read-only Journey v2 lens projections."""
from __future__ import annotations

from copy import deepcopy

from .evidence_json import canonical_sha256
from .journey_types import (
    EVENT_SCHEMA, OPERATIONAL_EVENT_TYPES, PROJECTION_SCHEMA, RECEIPT_STATES, STAGES,
    VERDICTS, build_event, require, require_text, validate_event, validate_journey_ref,
)

_LENSES = {
    "rescue": ("next_actions", "claims", "checks", "facts"),
    "diagnose": ("claims", "checks", "facts", "next_actions"),
    "verify": ("checks", "facts", "claims", "next_actions"),
}


def new_genesis(*, journey_ref: str, legacy_label: str | None, goal: str, intake: dict,
                actor_id: str, occurred_at: str) -> dict:
    """Create the sealed intake event; v2 refs are opaque, never filesystem paths."""
    validate_journey_ref(journey_ref)
    require(legacy_label is None or type(legacy_label) is str, "legacy_label must be str or null")
    require_text(goal, "goal")
    require(type(intake) is dict, "intake must be an object")
    request = {
        "journey_ref": journey_ref, "legacy_label": legacy_label, "goal": goal,
        "intake": intake, "actor_id": actor_id, "occurred_at": occurred_at,
    }
    return build_event(
        journey_ref=journey_ref, sequence=0, event_type="intake", occurred_at=occurred_at,
        actor_id=actor_id, request_sha256=canonical_sha256(request),
        payload={"legacy_label": legacy_label, "goal": goal, "intake": intake},
        prior_event_sha256=None,
    )


def _require_record(item: object, kind: str, required: set[str]) -> dict:
    require(type(item) is dict and required <= item.keys(), f"{kind} is incomplete")
    require_text(item.get(f"{kind}_id"), f"{kind}_id")
    require_text(item.get("does_not_prove"), "does_not_prove")
    refs = item.get("receipt_refs")
    require(type(refs) is list and refs, f"{kind} requires receipt_refs")
    for ref in refs:
        require_text(ref, "receipt_refs")
    require(item.get("receipt_state") in RECEIPT_STATES, "receipt_state is not in the v2 enum")
    return deepcopy(item)


def _record_definitions(payload: dict, state: dict) -> None:
    for kind, identity in (("fact", "fact_id"), ("claim", "claim_id")):
        records = payload.get(f"{kind}s", [])
        require(type(records) is list, f"{kind}s must be a list")
        for item in records:
            required = {identity, "statement", "receipt_refs", "receipt_state", "does_not_prove"}
            if kind == "claim":
                required |= {"depends_on", "verdict"}
            record = _require_record(item, kind, required)
            require_text(record.get("statement"), "statement")
            if kind == "claim":
                require(record["verdict"] in VERDICTS, "verdict is not in the four-way enum")
                require(type(record["depends_on"]) is list, "depends_on must be a list")
            key = record[identity]
            definition = {name: value for name, value in record.items()
                          if name not in ("verdict", "receipt_state")}
            prior = state[f"{kind}s"].get(key)
            require(prior is None or prior["definition"] == definition,
                    f"{kind} definition is immutable")
            state[f"{kind}s"][key] = {"definition": definition, "record": record}


def _record_checks(payload: dict, state: dict) -> None:
    checks = payload.get("checks", [])
    require(type(checks) is list, "checks must be a list")
    for item in checks:
        record = _require_record(item, "check", {
            "check_id", "claim_id", "verdict", "receipt_refs", "receipt_state",
            "numerator", "denominator", "does_not_prove",
        })
        require(record["verdict"] in VERDICTS, "verdict is not in the four-way enum")
        require(type(record["numerator"]) is int and type(record["denominator"]) is int
                and 0 <= record["numerator"] <= record["denominator"],
                "check numerator and denominator are invalid")
        require(record["claim_id"] in state["claims"], "check cites an unknown claim")
        state["checks"][record["check_id"]] = record


def _apply_payload(event: dict, state: dict) -> None:
    payload = event["payload"]
    _record_definitions(payload, state)
    _record_checks(payload, state)
    actions = payload.get("next_actions", [])
    require(type(actions) is list, "next_actions must be a list")
    state["next_actions"].extend(deepcopy(actions))
    if event["event_type"] == "concluded":
        require("conclusion" in payload, "concluded event requires conclusion")
        state["conclusion"] = deepcopy(payload["conclusion"])


def _projection(events: list[dict], state: dict, stage: str) -> dict:
    facts = {key: value["record"] for key, value in state["facts"].items()}
    claims = {key: value["record"] for key, value in state["claims"].items()}
    missing = []
    for kind, rows in (("fact", facts), ("claim", claims), ("check", state["checks"])):
        missing.extend({"kind": kind, "id": key, "receipt_refs": row["receipt_refs"]}
                       for key, row in rows.items() if row["receipt_state"] == "missing")
    return {
        "schema": PROJECTION_SCHEMA, "journey_ref": events[0]["journey_ref"],
        "event_head_sha256": events[-1]["event_sha256"], "fact_ids": sorted(facts),
        "claim_ids": sorted(claims), "checks": [state["checks"][key] for key in sorted(state["checks"])],
        "verdicts": {key: claims[key]["verdict"] for key in sorted(claims)},
        "missing_evidence": sorted(missing, key=lambda row: (row["kind"], row["id"])),
        "stage": stage, "conclusion": state["conclusion"], "facts": facts, "claims": claims,
        "next_actions": state["next_actions"],
    }


def reduce_events(events: list[dict]) -> dict:
    """Reduce one continuous immutable chain into its durable v2 projection."""
    require(type(events) is list and events, "events must be a non-empty list")
    state = {"facts": {}, "claims": {}, "checks": {}, "next_actions": [], "conclusion": None}
    journey_ref, head, stage = None, None, None
    for sequence, raw in enumerate(events):
        event = validate_event(raw)
        require(event["sequence"] == sequence, "event sequence is not continuous")
        require(journey_ref is None or event["journey_ref"] == journey_ref, "journey_ref changed")
        require(event["prior_event_sha256"] == head, "prior_event_sha256 does not match head")
        if sequence == 0:
            require(event["event_type"] == "intake" and head is None, "genesis must be intake")
            journey_ref, stage = event["journey_ref"], "intake"
        elif event["event_type"] in STAGES:
            require(event["event_type"] == STAGES[STAGES.index(stage) + 1], "stage transition invalid")
            stage = event["event_type"]
        else:
            require(event["event_type"] in OPERATIONAL_EVENT_TYPES, "operational event is invalid")
        _apply_payload(event, state)
        head = event["event_sha256"]
    return _projection(events, state, stage)


def project_lens(projection: dict, lens: str) -> dict:
    """Return one lens that changes presentation order but no evidence facts."""
    require(type(projection) is dict and projection.get("schema") == PROJECTION_SCHEMA,
            "projection schema is not v2")
    require(type(lens) is str and lens.lower() in _LENSES, "lens must be Rescue, Diagnose, or Verify")
    view, name = deepcopy(projection), lens.lower()
    view["lens"] = name.title()
    view["presentation"] = {key: deepcopy(projection[key]) for key in _LENSES[name]}
    return view
