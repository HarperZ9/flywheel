import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand


OWNER = "owner-crash"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ACKNOWLEDGED = "jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _command(*, head=None, request_id="create", marker="genesis", journey_ref=JOURNEY):
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
        owner_ref=OWNER, journey_ref=journey_ref, expected_event_head=head,
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

    committed_before_error = crash_point == "before_directory_fsync"
    if crash_point == "before_head_replace":
        with pytest.raises(JourneyStoreError) as inconsistent:
            JourneyStore(tmp_path).load(OWNER, JOURNEY)
        assert inconsistent.value.code == "STORE_COMMIT_FAILED"
    else:
        visible = JourneyStore(tmp_path).load(OWNER, JOURNEY)
        assert (visible["event_head_sha256"] != genesis.event_head_sha256) is committed_before_error

    retry = JourneyStore(tmp_path).append(mutation)
    assert retry.idempotent_replay is committed_before_error
    assert JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"] == retry.event_head_sha256
    events = _events(tmp_path)
    assert [event["sequence"] for event in events] == [0, 1]
    assert len({event["event_sha256"] for event in events}) == 2


@pytest.mark.parametrize("crash_point", (
    "before_event_fsync",
    "before_projection_replace",
    "before_head_replace",
    "before_directory_fsync",
))
def test_failed_create_residue_never_poisons_owner_listing(tmp_path, crash_point):
    """Treating a headless failed genesis as a Journey would break acknowledged listing."""
    healthy = JourneyStore(tmp_path)
    acknowledged = healthy.create(_command(
        request_id="acknowledged", journey_ref=ACKNOWLEDGED,
    ))

    def fail_at(point):
        if point == crash_point:
            raise OSError("injected create failure")

    with pytest.raises(JourneyStoreError) as failure:
        JourneyStore(tmp_path, fault_injector=fail_at).create(_command())
    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"
    listed = JourneyStore(tmp_path).list(OWNER)
    refs = [projection["journey_ref"] for projection in listed]
    assert ACKNOWLEDGED in refs
    assert next(item for item in listed if item["journey_ref"] == ACKNOWLEDGED)[
        "event_head_sha256"
    ] == acknowledged.event_head_sha256
    assert (JOURNEY in refs) is (crash_point == "before_directory_fsync")


def test_host_detail_runtime_error_from_fault_injector_is_normalized(tmp_path):
    """Allowing an injector RuntimeError through would violate fixed error transport."""
    store = JourneyStore(tmp_path)
    genesis = store.create(_command())

    def expose_host_detail(_point):
        raise RuntimeError(r"C:\private\operator\secret")

    mutation = _command(head=genesis.event_head_sha256, request_id="runtime-error")
    with pytest.raises(JourneyStoreError) as failure:
        JourneyStore(tmp_path, fault_injector=expose_host_detail).append(mutation)
    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"
    assert "private" not in str(failure.value)


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
