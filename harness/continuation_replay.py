"""Replay validation helpers for continuation-backed Journey mutations."""
from __future__ import annotations

from .evidence_json import canonical_sha256
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .journey_projection import reduce_events
from .journey_store import JourneyStore, JourneyStoreError, REQUEST_SCHEMA

ACK_SCHEMA = "flywheel.evidence-journey-mutation-ack/v2"


def ack_from_record(record: dict, event: dict, events: list[dict]) -> dict:
    sequence = record.get("sequence")
    expected = {
        "schema", "client_request_sha256", "request_sha256", "sequence",
        "event_head_sha256", "event_sha256", "projection_sha256",
    }
    if (set(record) != expected or record.get("schema") != REQUEST_SCHEMA
            or type(sequence) is not int or sequence != event.get("sequence")
            or record.get("event_head_sha256") != event.get("event_sha256")
            or record.get("event_sha256") != event.get("event_sha256")
            or record.get("request_sha256") != event.get("request_sha256")
            or record.get("projection_sha256") != canonical_sha256(
                reduce_events(events[:sequence + 1]))):
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return {"schema": ACK_SCHEMA, "journey_ref": event["journey_ref"],
            "event_head_sha256": record["event_head_sha256"],
            "event_sha256": record["event_sha256"],
            "projection_sha256": record["projection_sha256"],
            "idempotent_replay": True}


def matching_request_event(store: JourneyStore, *, owner_ref: str,
                           journey_ref: str | None,
                           request_id: str) -> tuple[dict, dict, list[dict]] | None:
    request_key = canonical_sha256(request_id)
    projections = [store.load(owner_ref, journey_ref)] if journey_ref else store.list(owner_ref)
    for projection in projections:
        ref = projection["journey_ref"]
        directory = store._journey_dir(owner_ref, ref)
        request_path = directory / "requests" / f"{request_key}.json"
        if not request_path.exists():
            continue
        try:
            with ExclusiveJourneyLock.acquire(
                    directory / ".lock", store.lock_timeout_s):
                head = store._read_head(directory)
                events = store._events_at_head(directory, head) if head else []
                record = store._read_json(request_path)
                if record.get("client_request_sha256") != request_key:
                    raise JourneyStoreError("STORE_COMMIT_FAILED")
                event = next((item for item in events
                              if item["event_sha256"] == record.get("event_sha256")), None)
                if event is None:
                    raise JourneyStoreError("STORE_COMMIT_FAILED")
                return record, event, events
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
    return None
