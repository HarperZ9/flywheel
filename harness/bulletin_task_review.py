"""Project independently checked Bulletin tasks into existing Journey v2."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .bulletin_task_contract import evaluate_handoff, validate_contract
from .evidence_json import canonical_bytes, canonical_sha256
from .journey_projection import new_genesis, reduce_events
from .journey_types import build_event
from .private_artifact_fs import open_artifact_root


def build_review(contract: object, observation: object) -> dict:
    c = validate_contract(contract)
    result = evaluate_handoff(c, observation)
    digest = canonical_sha256(result)
    ref = "jrn_" + digest[:32]
    at = datetime.now(timezone.utc).isoformat()
    genesis = new_genesis(journey_ref=ref, legacy_label=None,
        goal="Independently check one bounded Bulletin handoff",
        intake={"task_id": c["task_id"], "contract_sha256": result["contract_sha256"]},
        actor_id="bulletin-task-observer", occurred_at=at)
    state = "MATCH" if result["verdict"] == "PASS" else "UNVERIFIABLE"
    common = {"receipt_refs": ["sha256:" + digest], "receipt_state": state,
              "does_not_prove": " ".join(result["does_not_prove"])}
    payload = {
        "facts": [{"fact_id": "observed-handoff", "statement":
            "The independent observer supplied bounded public-board evidence.", **common}],
        "claims": [{"claim_id": "handoff", "statement":
            "The observed reply meets the external task contract.",
            "depends_on": [], "verdict": result["verdict"], **common}],
        "checks": [{"check_id": "handoff-oracle", "claim_id": "handoff",
            "verdict": result["verdict"], **result["task_success"], **common}],
    }
    event = build_event(journey_ref=ref, sequence=1, event_type="record_fact",
        occurred_at=at, actor_id="bulletin-task-observer",
        request_sha256=canonical_sha256(payload), payload=payload,
        prior_event_sha256=genesis["event_sha256"])
    events = [genesis, event]
    reduce_events(events)  # Reject any drift from the shared Journey contract.
    return {"schema": "flywheel.bulletin-task-review/v1", "contract": c,
            "observation": observation, "result": result, "journey_events": events}


def write_review(root: Path, review: dict) -> None:
    """Publish to an existing private artifact root without overwriting conflicts."""
    with open_artifact_root(root) as store:
        store.write_new_or_same("review.json", canonical_bytes(review))
