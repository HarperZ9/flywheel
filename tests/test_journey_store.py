from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from threading import Barrier

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.journey_lock import ExclusiveJourneyLock


OWNER = "owner-1"
JOURNEY = "jrn_0123456789abcdef0123456789abcdef"


def _create_command(request_id="create-1"):
    return MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=None,
        client_request_id=request_id, operation="intake",
        body={
            "legacy_label": "repair-1", "goal": "Explain the failed verification",
            "intake": {"receipt_refs": ["receipt:intake"]},
            "occurred_at": "2026-08-14T12:00:00Z",
        },
    )


def _append_command(head, request_id="append-1", marker="one"):
    return MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id=request_id, operation="record_next_action",
        body={
            "occurred_at": "2026-08-14T12:01:00Z",
            "payload": {"next_actions": [{"marker": marker}]},
        },
    )


def _journey_dir(root):
    return root / "journeys" / "v2" / "owners" / OWNER / JOURNEY


def _stored_events(root):
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((_journey_dir(root) / "events").glob("*.json"))]


def test_create_persists_a_hash_bound_head_projection_and_event(tmp_path):
    """Removing any durable artifact or hash binding must break a reopened load."""
    store = JourneyStore(tmp_path)
    command = _create_command()
    ack = store.create(command)
    projection = JourneyStore(tmp_path).load(OWNER, JOURNEY)
    journey_dir = _journey_dir(tmp_path)
    head = json.loads((journey_dir / "head.json").read_text(encoding="utf-8"))
    events = _stored_events(tmp_path)

    assert ack.journey_ref == JOURNEY
    assert ack.event_head_sha256 == ack.event_sha256 == events[0]["event_sha256"]
    assert ack.projection_sha256 == canonical_sha256(projection)
    assert ack.idempotent_replay is False
    assert head == {
        "schema": "flywheel.evidence-journey-head/v2", "journey_ref": JOURNEY,
        "sequence": 0, "event_head_sha256": ack.event_head_sha256,
        "projection_sha256": ack.projection_sha256,
    }
    assert projection["event_head_sha256"] == ack.event_head_sha256
    assert events[0]["actor_id"] == OWNER
    assert events[0]["request_sha256"] == canonical_sha256({
        "owner_ref": OWNER, "journey_ref": JOURNEY, "expected_event_head": None,
        "operation": command.operation, "body": command.body,
    })
    assert b"create-1" not in b"".join(path.read_bytes() for path in journey_dir.rglob("*.*"))


def test_same_idempotency_key_replays_only_the_identical_canonical_request(tmp_path):
    """Dropping request digest comparison would duplicate or silently change a mutation."""
    store = JourneyStore(tmp_path)
    genesis = store.create(_create_command())
    command = _append_command(genesis.event_head_sha256)
    first = store.append(command)
    replay = JourneyStore(tmp_path).append(command)

    assert replay == replace(first, idempotent_replay=True)
    changed = replace(command, body={**command.body, "payload": {"next_actions": []}})
    with pytest.raises(JourneyStoreError) as failure:
        store.append(changed)
    assert failure.value.code == str(failure.value) == "IDEMPOTENCY_MISMATCH"
    assert len(_stored_events(tmp_path)) == 2


def test_corrupt_idempotency_record_cannot_forge_a_replay_ack(tmp_path):
    """Trusting stored ack fields without rederivation would acknowledge forged state."""
    store = JourneyStore(tmp_path)
    genesis = store.create(_create_command())
    command = _append_command(genesis.event_head_sha256)
    store.append(command)
    request_path = next((_journey_dir(tmp_path) / "requests").glob("*.json"))
    for candidate in (_journey_dir(tmp_path) / "requests").glob("*.json"):
        record = json.loads(candidate.read_text(encoding="utf-8"))
        if record["sequence"] == 1:
            request_path, record = candidate, record
            break
    record["projection_sha256"] = "0" * 64
    request_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(JourneyStoreError) as failure:
        JourneyStore(tmp_path).append(command)
    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"


def test_cas_conflict_and_busy_lock_are_fixed_non_echoing_failures(tmp_path):
    """Skipping lock/CAS or echoing host errors would permit overwrite or disclosure."""
    store = JourneyStore(tmp_path, lock_timeout_s=0.01)
    genesis = store.create(_create_command())
    winning = store.append(_append_command(genesis.event_head_sha256))
    with pytest.raises(JourneyStoreError) as conflict:
        store.append(_append_command(genesis.event_head_sha256, "append-2", "two"))
    assert conflict.value.code == str(conflict.value) == "HEAD_CONFLICT"
    assert store.load(OWNER, JOURNEY)["event_head_sha256"] == winning.event_head_sha256

    lock_path = _journey_dir(tmp_path) / ".lock"
    with ExclusiveJourneyLock.acquire(lock_path):
        with pytest.raises(JourneyStoreError) as busy:
            store.append(_append_command(winning.event_head_sha256, "append-3", "three"))
    assert busy.value.code == str(busy.value) == "STORE_BUSY"


def test_load_and_list_are_owner_scoped_and_return_canonical_projections(tmp_path):
    """Selecting by label or another owner would cross the server custody boundary."""
    first = JourneyStore(tmp_path)
    ack = first.create(_create_command())
    second_owner = replace(
        _create_command("create-2"), owner_ref="owner-2",
        journey_ref="jrn_fedcba9876543210fedcba9876543210",
    )
    second = first.create(second_owner)

    assert [item["journey_ref"] for item in first.list(OWNER)] == [JOURNEY]
    assert first.load(OWNER, JOURNEY)["event_head_sha256"] == ack.event_head_sha256
    assert first.list("owner-2")[0]["event_head_sha256"] == second.event_head_sha256
    with pytest.raises(JourneyStoreError) as missing:
        first.load("owner-2", JOURNEY)
    assert missing.value.code == str(missing.value) == "JOURNEY_NOT_FOUND"


def test_missing_replay_lookup_is_read_only(tmp_path):
    """Creating directories during a pre-grant lookup would mutate server state."""
    root = tmp_path / "absent-state"
    assert JourneyStore(root).lookup_replay(_create_command()) is None
    assert not root.exists()


@pytest.mark.parametrize("case", range(20))
def test_twenty_cases_have_one_two_writer_cas_winner_and_no_duplicate_sequence(tmp_path, case):
    """Removing the under-lock head reread would allow both writers at one head."""
    genesis = JourneyStore(tmp_path).create(_create_command(f"create-{case}"))
    barrier = Barrier(2)

    def race(request_id, marker):
        barrier.wait()
        try:
            return JourneyStore(tmp_path).append(
                _append_command(genesis.event_head_sha256, request_id, marker),
            )
        except JourneyStoreError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda args: race(*args),
            ((f"left-{case}", "left"), (f"right-{case}", "right")),
        ))
    winners = [result for result in results if not isinstance(result, str)]
    assert len(winners) == 1
    assert results.count("HEAD_CONFLICT") == 1
    events = _stored_events(tmp_path)
    assert [event["sequence"] for event in events] == [0, 1]
    assert len({event["event_sha256"] for event in events}) == 2
    assert JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"] == (
        winners[0].event_head_sha256
    )
