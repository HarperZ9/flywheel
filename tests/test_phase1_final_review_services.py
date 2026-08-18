from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.grant_route import grant_post
from harness.journey_checks import CheckCommand, JourneyCheckService
from harness.journey_projection import project_lens, reduce_events
from harness.journey_store import JourneyStore, JourneyStoreError, MutationCommand
from harness.operation_grants import GrantRequest, GrantStore
from harness.operation_supervisor import OperationSupervisor

NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
JOURNEY = "jrn_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
OPERATION = "op_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _store_create(root, request_id="create"):
    return JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, request_id, "intake",
        {"legacy_label": None, "goal": "Bounded", "intake": {},
         "occurred_at": NOW}))


def _write_version(root, version):
    path = root / "journeys" / "version.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes({
        "schema": "flywheel.evidence-journey-store-version/v1",
        "version": version}))


def _event(ref, sequence, event_type, payload, prior):
    event = {"schema": "flywheel.evidence-journey-event/v2",
        "journey_ref": ref, "sequence": sequence, "event_type": event_type,
        "occurred_at": NOW, "actor_id": OWNER,
        "request_sha256": canonical_sha256({"n": sequence}),
        "payload": payload, "prior_event_sha256": prior}
    return {**event, "event_sha256": canonical_sha256(event)}


def test_lenses_match_source_projection_directly_and_do_not_mutate_it():
    """A lens may reorder presentation but cannot rewrite source evidence."""
    genesis = _event(JOURNEY, 0, "intake", {
        "legacy_label": None, "goal": "Bounded", "intake": {}}, None)
    claim = _event(JOURNEY, 1, "record_claim", {"claims": [{
        "claim_id": "claim-1", "statement": "Claim",
        "depends_on": [], "receipt_refs": ["receipt.json"],
        "receipt_state": "MATCH", "verdict": "FAIL",
        "does_not_prove": "success"}]}, genesis["event_sha256"])
    source = reduce_events([genesis, claim])
    frozen = deepcopy(source)
    keys = ("journey_ref", "event_head_sha256", "fact_ids", "claim_ids",
            "checks", "verdicts", "missing_evidence", "stage", "conclusion")
    for lens in ("rescue", "diagnose", "verify"):
        view = project_lens(source, lens)
        assert {key: view[key] for key in keys} == {key: source[key] for key in keys}
        view["claims"]["claim-1"]["statement"] = "mutated"
        view["presentation"][next(iter(view["presentation"]))] = "mutated"
        assert source == frozen


def test_store_version_requires_exact_int_before_mutation(tmp_path):
    """JSON 2.0 must not compare equal to supported integer version 2."""
    _write_version(tmp_path, 2.0)
    with pytest.raises(JourneyStoreError) as failure:
        _store_create(tmp_path)
    assert failure.value.code == "VERSION_MISMATCH"
    assert not (tmp_path / "journeys" / "v2").exists()


def test_nested_unhashable_action_kind_is_typed_and_persists_nothing(tmp_path):
    """Unhashable nested metadata must not escape as a 500 or write a proposal."""
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    evidence.mkdir()
    body = {"journey_ref": JOURNEY, "expected_event_head": "a" * 64,
        "client_request_id": "append-1", "command": {
            "type": "record_next_action",
            "next_action": {"action_id": "a1", "kind": ["inspect"],
                "description": "Inspect", "basis_refs": ["claim-1"]}}}
    result, status = grant_post(
        "/api/grants/prepare/append", canonical_bytes(body), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    assert status == 422 and result["error"]["code"] == "INVALID_TRANSITION"
    assert not state.exists()


def _check_service(root, *, oracle_id="missing", supported=frozenset(("measurement",))):
    genesis = _store_create(root)
    from harness.journey_service import JourneyService
    journey = JourneyService(owner_ref=OWNER, store=JourneyStore(root),
        grants=GrantStore(root, clock=lambda: NOW), clock=lambda: NOW)
    service = JourneyCheckService(journey=journey, supported_oracle_types=supported)
    context = {"candidate_ref": "candidate.json", "task_id": "safe"}
    arguments = {"client_request_id": "check-1", "operation_ref": OPERATION,
        "journey_sha256": canonical_sha256({"schema": "legacy"}),
        "claim_id": "claim-1", "oracle_id": oracle_id,
        "artifact_root_ref": "artifacts", "candidate_ref": "candidate.json",
        "context_sha256": canonical_sha256(context),
        "context_bytes_sha256": hashlib.sha256(canonical_bytes(context)).hexdigest()}
    operation = {"owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": genesis.event_head_sha256,
        "operation": "check", "body": arguments}
    request = GrantRequest(OWNER, JOURNEY, genesis.event_head_sha256,
        canonical_sha256(operation), "journey.check",
        canonical_sha256(arguments), ("journey:check",),
        ("artifacts", "candidate.json"), "2026-08-14T12:02:00Z",
        "check-1")
    grant_ref = journey.grants.issue(request, approved=True)["grant_ref"]
    command = CheckCommand(OWNER, JOURNEY, genesis.event_head_sha256,
        "check-1", OPERATION, grant_ref, request, {"schema": "legacy"},
        "claim-1", oracle_id, "candidate.json", context,
        arguments["context_bytes_sha256"], "artifacts")
    return service, command, grant_ref, request


def test_direct_check_validates_unavailable_operation_before_grant_consumption(tmp_path):
    """A direct unavailable oracle check must not burn exact approval."""
    service, command, grant_ref, request = _check_service(tmp_path)
    ack = service.request(command)
    assert ack.event_head_sha256
    assert service.state(OPERATION) == "blocked"
    consumed = GrantStore(tmp_path, clock=lambda: NOW).consume(
        grant_ref, request, now=NOW)
    assert consumed["consumed"] is True


class Process:
    def __init__(self):
        self.signal_calls = 0
    def signal_tree(self):
        self.signal_calls += 1
        return False
    def wait(self, _timeout_s):
        raise AssertionError("wait should not run after failed signal")


def _cancel_request(root, head, request_id):
    body = {"client_request_id": request_id, "operation_ref": OPERATION,
            "timeout_s": 5.0}
    operation = {"owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": head, "operation": "cancel", "body": body}
    request = GrantRequest(OWNER, JOURNEY, head, canonical_sha256(operation),
        "journey.cancel", canonical_sha256(body), ("journey:cancel",), (),
        "2026-08-14T12:02:00Z", request_id)
    grant_ref = GrantStore(root, clock=lambda: NOW).issue(
        request, approved=True)["grant_ref"]
    return request, grant_ref


def test_repeated_cancel_with_new_request_does_not_append_or_consume_again(tmp_path):
    """An unterminated cancel_requested is a state, not authority to append again."""
    service, command, _grant_ref, _request = _check_service(
        tmp_path, oracle_id="ml", supported=frozenset(("measurement",)))
    started = service.request(command)
    process = Process()
    requests = {}
    first_req, first_grant = _cancel_request(tmp_path, started.event_head_sha256,
                                             "cancel-1")
    second_req, second_grant = _cancel_request(tmp_path, started.event_head_sha256,
                                              "cancel-2")
    requests.update({first_grant: first_req, second_grant: second_req})
    supervisor = OperationSupervisor(
        check_service=service, grant_request=lambda ref: requests[ref])
    supervisor.register_owned(owner_ref=OWNER, journey_ref=JOURNEY,
                              operation_ref=OPERATION, process=process)
    first = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-1", operation_ref=OPERATION,
        grant_ref=first_grant, timeout_s=5.0)
    before = _events(tmp_path)
    second = supervisor.request_cancel(
        owner_ref=OWNER, journey_ref=JOURNEY,
        expected_event_head=started.event_head_sha256,
        client_request_id="cancel-2", operation_ref=OPERATION,
        grant_ref=second_grant, timeout_s=5.0)
    assert first == second == {
        "code": "CANCEL_UNAVAILABLE", "operation_ref": OPERATION,
        "state": "cancel_requested"}
    assert _events(tmp_path) == before
    assert process.signal_calls == 1
    consumed = GrantStore(tmp_path, clock=lambda: NOW).consume(
        second_grant, second_req, now=NOW)
    assert consumed["consumed"] is True


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def test_fixture_binds_each_command_to_grant_and_observed_effect():
    """The durable-restart fixture must specify the executed flow it proves."""
    fixture = json.loads(Path(
        "benchmarks/fixtures/evidence-journey/durable-restart-v2.json"
    ).read_text(encoding="utf-8"))
    for item in fixture["commands"]:
        assert set(item) == {
            "action", "client_request_id", "grant_prepare", "grant_approve",
            "expected_status", "expected_error", "expected_effect"}
