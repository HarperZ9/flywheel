import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand


OWNER = "owner-crash"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _command(*, head=None, request_id="create", marker="genesis"):
    if head is None:
        body = {
            "legacy_label": None, "goal": "Preserve acknowledged evidence",
            "intake": {"marker": marker}, "occurred_at": "2026-08-14T12:00:00Z",
        }
        operation = "intake"
    else:
        body = {
            "occurred_at": "2026-08-14T12:01:00Z",
            "payload": {"next_actions": [{"marker": marker}]},
        }
        operation = "record_next_action"
    return MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id=request_id, operation=operation, body=body,
    )


def _events(root):
    path = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(item.read_text(encoding="utf-8")) for item in sorted(path.glob("*.json"))]


@pytest.mark.parametrize("crash_point", (
    "before_event_fsync",
    "before_projection_replace",
    "before_head_replace",
    "before_directory_fsync",
))
def test_each_crash_point_fails_closed_and_an_identical_retry_converges(tmp_path, crash_point):
    """Returning or losing an acknowledged head across a crash would violate durability."""
    healthy = JourneyStore(tmp_path)
    genesis = healthy.create(_command())
    mutation = _command(head=genesis.event_head_sha256, request_id="append", marker=crash_point)

    def fail_at(point):
        if point == crash_point:
            raise OSError(r"C:\private\operator\secret")

    broken = JourneyStore(tmp_path, fault_injector=fail_at)
    with pytest.raises(JourneyStoreError) as failure:
        broken.append(mutation)
    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"
    assert "private" not in str(failure.value)

    visible = JourneyStore(tmp_path).load(OWNER, JOURNEY)
    committed_before_error = crash_point == "before_directory_fsync"
    assert (visible["event_head_sha256"] != genesis.event_head_sha256) is committed_before_error

    retry = JourneyStore(tmp_path).append(mutation)
    assert retry.idempotent_replay is committed_before_error
    assert JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"] == retry.event_head_sha256
    events = _events(tmp_path)
    assert [event["sequence"] for event in events] == [0, 1]
    assert len({event["event_sha256"] for event in events}) == 2


def test_success_is_acknowledged_only_after_reopen_matches_every_ack_digest(tmp_path):
    """Acknowledging before the durable head/projection match would create acknowledged loss."""
    store = JourneyStore(tmp_path)
    genesis = store.create(_command())
    appended = store.append(_command(
        head=genesis.event_head_sha256, request_id="append", marker="durable",
    ))
    reopened = JourneyStore(tmp_path).load(OWNER, JOURNEY)

    assert reopened["event_head_sha256"] == appended.event_head_sha256
    assert reopened["event_head_sha256"] == appended.event_sha256
    assert canonical_sha256(reopened) == appended.projection_sha256
