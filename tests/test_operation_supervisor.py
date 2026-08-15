import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_checks import CheckCommand, JourneyCheckService
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, MutationCommand
from harness.operation_grants import GrantRequest, GrantStore
from harness.operation_supervisor import OperationSupervisor


NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
JOURNEY = "jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OPERATION = "op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def _check_service(root):
    store = JourneyStore(root)
    genesis = store.create(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=None,
        client_request_id="genesis", operation="intake",
        body={"legacy_label": None, "goal": "Control cancellation", "intake": {},
              "occurred_at": NOW},
    ))
    grants = GrantStore(root, clock=lambda: NOW)
    journey = JourneyService(
        owner_ref=OWNER, store=store, grants=grants, clock=lambda: NOW,
    )
    service = JourneyCheckService(journey=journey)
    candidate = root / "candidate.json"
    context = {
        "task_id": "cancel-v1", "prompt": "Check measurement",
        "oracle_cmd": "measurement_gate", "candidate_ref": candidate.name,
        "raw_artifact_refs": [candidate.name], "timeout_seconds": 10,
    }
    legacy = {"schema": "controlled-test-journey/v1", "claim": "claim-root"}
    arguments = {
        "journey_sha256": canonical_sha256(legacy), "claim_id": "claim-root",
        "oracle_id": "ml", "candidate_ref": candidate.name,
        "context_sha256": canonical_sha256(context),
    }
    operation = {
        "owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": genesis.event_head_sha256,
        "operation": "check", "body": arguments,
    }
    request = GrantRequest(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=genesis.event_head_sha256,
        operation_sha256=canonical_sha256(operation), tool="journey.check",
        arguments_sha256=canonical_sha256(arguments), scopes=("journey:check",),
        data_refs=(candidate.name,), expires_at="2026-08-14T12:02:00Z",
        nonce="start",
    )
    grant_ref = grants.issue(request, approved=True)["grant_ref"]
    command = CheckCommand(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=genesis.event_head_sha256,
        client_request_id="check-start", operation_ref=OPERATION,
        grant_ref=grant_ref, grant_request=request, journey=legacy,
        claim_id="claim-root", oracle_id="ml", candidate=candidate,
        context=context, artifact_root=root,
    )
    started = service.request(command)
    return service, grants, started


def _cancel_request(grants, head, *, request_id="cancel-1", timeout_s=5.0):
    body = {
        "client_request_id": request_id, "operation_ref": OPERATION,
        "timeout_s": timeout_s,
    }
    operation = {
        "owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": head, "operation": "cancel", "body": body,
    }
    request = GrantRequest(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation_sha256=canonical_sha256(operation), tool="journey.cancel",
        arguments_sha256=canonical_sha256(body), scopes=("journey:cancel",),
        data_refs=(), expires_at="2026-08-14T12:02:00Z", nonce=request_id,
    )
    grant_ref = grants.issue(request, approved=True)["grant_ref"]
    return request, grant_ref


class Process:
    def __init__(self, *, signalled=True, terminal="cancelled"):
        self.signalled, self.terminal = signalled, terminal
        self.signal_calls, self.wait_calls = 0, []

    def signal_tree(self):
        self.signal_calls += 1
        return self.signalled

    def wait(self, timeout_s):
        self.wait_calls.append(timeout_s)
        return self.terminal


def _supervisor(service, grants, head, process, *, timeout_s=5.0):
    request, grant_ref = _cancel_request(grants, head, timeout_s=timeout_s)
    requests = {grant_ref: request}
    supervisor = OperationSupervisor(
        check_service=service, grant_request=lambda ref: requests[ref],
    )
    supervisor.register_owned(
        owner_ref=OWNER, journey_ref=JOURNEY,
        operation_ref=OPERATION, process=process,
    )
    return supervisor, grant_ref


def test_cancel_signals_only_registered_tree_then_commits_cancelled(tmp_path):
    """Signalling another process or labelling before wait would make Stop unsafe."""
    service, grants, started = _check_service(tmp_path)
    owned, unrelated = Process(), Process()
    supervisor, grant_ref = _supervisor(service, grants, started.event_head_sha256, owned)

    result = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=grant_ref, timeout_s=5.0,
    )

    assert result["state"] == "cancelled" and "code" not in result
    assert owned.signal_calls == 1 and owned.wait_calls == [5.0]
    assert unrelated.signal_calls == 0
    assert [event["event_type"] for event in _events(tmp_path)[-2:]] == [
        "cancel_requested", "check_cancelled",
    ]


@pytest.mark.parametrize("signalled,terminal", ((False, "cancelled"), (True, None)))
def test_uncontrolled_cancel_stays_requested_and_returns_cancel_unavailable(
        tmp_path, signalled, terminal):
    """A failed signal or bounded wait must never be reported as cancelled."""
    service, grants, started = _check_service(tmp_path)
    process = Process(signalled=signalled, terminal=terminal)
    supervisor, grant_ref = _supervisor(service, grants, started.event_head_sha256, process)

    result = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=grant_ref, timeout_s=5.0,
    )

    assert result == {
        "code": "CANCEL_UNAVAILABLE", "operation_ref": OPERATION,
        "state": "cancel_requested",
    }
    types = [event["event_type"] for event in _events(tmp_path)]
    assert types.count("cancel_requested") == 1
    assert types.count("check_cancelled") == 0


def test_completion_during_cancel_commits_completed_not_cancelled(tmp_path):
    """A raced natural completion cannot truthfully become a cancellation."""
    service, grants, started = _check_service(tmp_path)
    process = Process(terminal="completed")
    supervisor, grant_ref = _supervisor(service, grants, started.event_head_sha256, process)

    result = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=grant_ref, timeout_s=5.0,
    )

    assert result["state"] == "completed"
    assert _events(tmp_path)[-1]["event_type"] == "check_completed"


def test_identical_cancel_replays_before_grant_and_second_signal(tmp_path):
    """A retry after durable terminal state must not require or signal again."""
    service, grants, started = _check_service(tmp_path)
    process = Process()
    supervisor, grant_ref = _supervisor(service, grants, started.event_head_sha256, process)
    arguments = {
        "owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": started.event_head_sha256,
        "client_request_id": "cancel-1", "operation_ref": OPERATION,
        "timeout_s": 5.0,
    }
    first = supervisor.request_cancel(
        grant_ref=grant_ref, **arguments,
    )

    replay = supervisor.request_cancel(
        grant_ref="gnt_ffffffffffffffffffffffffffffffff", **arguments,
    )

    assert replay == first
    assert process.signal_calls == 1 and process.wait_calls == [5.0]
    assert [event["event_type"] for event in _events(tmp_path)].count(
        "check_cancelled") == 1


def test_wrong_owner_cannot_replay_or_discover_terminal_state(tmp_path):
    """Replay lookup before ownership would disclose another owner's terminal."""
    service, grants, started = _check_service(tmp_path)
    process = Process()
    supervisor, grant_ref = _supervisor(service, grants, started.event_head_sha256, process)
    supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=grant_ref, timeout_s=5.0,
    )

    result = supervisor.request_cancel(
        owner_ref="owner_cccccccccccccccccccccccccccccccc",
        journey_ref=JOURNEY, expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref="gnt_ffffffffffffffffffffffffffffffff", timeout_s=5.0,
    )

    assert result == {
        "code": "CANCEL_UNAVAILABLE", "operation_ref": OPERATION,
        "state": "unknown",
    }
    assert process.signal_calls == 1


def test_unowned_operation_returns_unavailable_without_signalling(tmp_path):
    """Looking up an arbitrary operation must not obtain a process-tree handle."""
    service, grants, started = _check_service(tmp_path)
    process = Process()
    request, grant_ref = _cancel_request(grants, started.event_head_sha256)
    supervisor = OperationSupervisor(
        check_service=service, grant_request=lambda _ref: request,
    )

    result = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=grant_ref, timeout_s=5.0,
    )

    assert result["code"] == "CANCEL_UNAVAILABLE"
    assert result["state"] == "running" and process.signal_calls == 0
    assert "cancel_requested" not in [event["event_type"] for event in _events(tmp_path)]


@pytest.mark.parametrize("timeout_s", (0.0, 30.1))
def test_cancel_timeout_is_positive_and_bounded_before_state_change(tmp_path, timeout_s):
    """An unbounded or zero wait would make terminal control unverifiable."""
    service, grants, started = _check_service(tmp_path)
    process = Process()
    request, grant_ref = _cancel_request(grants, started.event_head_sha256)
    supervisor = OperationSupervisor(
        check_service=service, grant_request=lambda _ref: request,
    )
    supervisor.register_owned(
        owner_ref=OWNER, journey_ref=JOURNEY,
        operation_ref=OPERATION, process=process,
    )

    with pytest.raises(ValueError, match="timeout_s is invalid"):
        supervisor.request_cancel(
            owner_ref=OWNER, journey_ref=JOURNEY,
            expected_event_head=started.event_head_sha256,
            client_request_id="cancel-1", operation_ref=OPERATION,
            grant_ref=grant_ref, timeout_s=timeout_s,
        )
    assert process.signal_calls == 0
    assert "cancel_requested" not in [event["event_type"] for event in _events(tmp_path)]
