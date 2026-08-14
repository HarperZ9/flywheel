from dataclasses import replace
import json
import re

import pytest

from harness.evidence_json import canonical_sha256
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore, JourneyStoreError
from harness.operation_grants import GrantError, GrantRequest, GrantStore


NOW = "2026-08-14T12:00:00Z"
OWNER_A = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OWNER_B = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _create_body(label="same-display-label"):
    return {
        "legacy_label": label, "goal": "Preserve exact evidence",
        "intake": {"receipt_refs": ["evidence/intake.json"]}, "occurred_at": NOW,
    }


def _grant_request(owner, tool, journey_ref, head, operation, body, nonce):
    operation_value = {
        "owner_ref": owner, "journey_ref": journey_ref,
        "expected_event_head": head, "operation": operation, "body": body,
    }
    return GrantRequest(
        owner_ref=owner, journey_ref=journey_ref, expected_event_head=head,
        operation_sha256=canonical_sha256(operation_value), tool=tool,
        arguments_sha256=canonical_sha256(body), scopes=("journey:mutate",),
        data_refs=("evidence/intake.json",), expires_at="2026-08-14T12:02:00Z",
        nonce=nonce,
    )


def _service(root, owner, *, fault_injector=None):
    return JourneyService(
        owner_ref=owner, store=JourneyStore(root),
        grants=GrantStore(root, clock=lambda: NOW), clock=lambda: NOW,
        fault_injector=fault_injector,
    )


def _approved_create(root, owner, body, nonce="create"):
    request = _grant_request(owner, "journey.create", None, None, "intake", body, nonce)
    issued = GrantStore(root, clock=lambda: NOW).issue(request, approved=True)
    return request, issued["grant_ref"]


def _create(root, owner, *, body=None, request_id="create-1", nonce="create"):
    body = body or _create_body()
    request, grant_ref = _approved_create(root, owner, body, nonce)
    return _service(root, owner).create(
        client_request_id=request_id, body=body, grant_ref=grant_ref,
        grant_request=request,
    )


def test_create_generates_opaque_ref_only_for_null_journey_and_head_binding(tmp_path):
    """Accepting a caller Journey selector at genesis would make storage path-selectable."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)
    ack = _service(tmp_path, OWNER_A).create(
        client_request_id="create-1", body=body, grant_ref=grant_ref,
        grant_request=request,
    )

    assert re.fullmatch(r"jrn_[0-9a-f]{32}", ack.journey_ref)
    assert _service(tmp_path, OWNER_A).resume(ack.journey_ref)["journey_ref"] == ack.journey_ref

    bad = replace(request, journey_ref="jrn_0123456789abcdef0123456789abcdef")
    with pytest.raises(GrantError) as failure:
        GrantStore(tmp_path, clock=lambda: NOW).issue(bad, approved=True)
    assert failure.value.code == str(failure.value) == "PERMISSION_DENIED"


def test_list_resume_and_legacy_label_are_bound_only_to_service_owner(tmp_path):
    """Selecting by display label or listing all owners would cross the custody boundary."""
    first = _create(tmp_path, OWNER_A, nonce="owner-a")
    second = _create(tmp_path, OWNER_B, request_id="create-2", nonce="owner-b")

    assert [item["journey_ref"] for item in _service(tmp_path, OWNER_A).list()] == [first.journey_ref]
    assert [item["journey_ref"] for item in _service(tmp_path, OWNER_B).list()] == [second.journey_ref]
    with pytest.raises(JourneyStoreError) as hidden:
        _service(tmp_path, OWNER_B).resume(first.journey_ref)
    assert hidden.value.code == str(hidden.value) == "JOURNEY_NOT_FOUND"
    with pytest.raises(ValueError):
        _service(tmp_path, OWNER_A).resume("same-display-label")


def test_append_binds_owner_journey_head_operation_and_body_then_burns_once(tmp_path):
    """Executing different mutation bytes under one approval would widen its authority."""
    genesis = _create(tmp_path, OWNER_A)
    body = {"occurred_at": NOW, "payload": {"next_actions": [{"marker": "one"}]}}
    request = _grant_request(
        OWNER_A, "journey.append", genesis.journey_ref, genesis.event_head_sha256,
        "record_next_action", body, "append",
    )
    issued = GrantStore(tmp_path, clock=lambda: NOW).issue(request, approved=True)
    service = _service(tmp_path, OWNER_A)
    changed = {"occurred_at": NOW, "payload": {"next_actions": [{"marker": "two"}]}}
    with pytest.raises(GrantError) as widened:
        service.append(
            journey_ref=genesis.journey_ref,
            expected_event_head=genesis.event_head_sha256,
            client_request_id="append-widened", operation="record_next_action",
            body=changed, grant_ref=issued["grant_ref"], grant_request=request,
        )
    assert widened.value.code == str(widened.value) == "PERMISSION_DENIED"

    ack = service.append(
        journey_ref=genesis.journey_ref, expected_event_head=genesis.event_head_sha256,
        client_request_id="append-1", operation="record_next_action", body=body,
        grant_ref=issued["grant_ref"], grant_request=request,
    )

    assert ack.event_head_sha256 != genesis.event_head_sha256
    with pytest.raises(GrantError) as reused:
        service.append(
            journey_ref=genesis.journey_ref, expected_event_head=ack.event_head_sha256,
            client_request_id="append-2", operation="record_next_action", body=changed,
            grant_ref=issued["grant_ref"], grant_request=request,
        )
    assert reused.value.code in {"PERMISSION_DENIED", "APPROVAL_EXPIRED"}


def test_identical_replay_returns_before_any_grant_lookup_or_consumption(tmp_path):
    """Consuming approval before replay lookup would make safe retries require new authority."""
    genesis = _create(tmp_path, OWNER_A)
    body = {"occurred_at": NOW, "payload": {"next_actions": [{"marker": "one"}]}}
    request = _grant_request(
        OWNER_A, "journey.append", genesis.journey_ref, genesis.event_head_sha256,
        "record_next_action", body, "append",
    )
    issued = GrantStore(tmp_path, clock=lambda: NOW).issue(request, approved=True)
    service = _service(tmp_path, OWNER_A)
    first = service.append(
        journey_ref=genesis.journey_ref, expected_event_head=genesis.event_head_sha256,
        client_request_id="same-request", operation="record_next_action", body=body,
        grant_ref=issued["grant_ref"], grant_request=request,
    )
    replay = service.append(
        journey_ref=genesis.journey_ref, expected_event_head=genesis.event_head_sha256,
        client_request_id="same-request", operation="record_next_action", body=body,
        grant_ref="gnt_does_not_exist", grant_request=request,
    )

    assert replay == replace(first, idempotent_replay=True)


def test_create_replay_is_found_before_generating_a_new_ref_or_requiring_a_grant(tmp_path, monkeypatch):
    """Generating first on retry would duplicate a logically identical Journey."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)
    service = _service(tmp_path, OWNER_A)
    first = service.create(
        client_request_id="same-create", body=body, grant_ref=grant_ref, grant_request=request,
    )
    monkeypatch.setattr(service, "_new_journey_ref", lambda: pytest.fail("generated ID"))
    replay = service.create(
        client_request_id="same-create", body=body, grant_ref="gnt_missing", grant_request=request,
    )

    assert replay == replace(first, idempotent_replay=True)
    assert [item["journey_ref"] for item in service.list()] == [first.journey_ref]


def test_new_create_generates_id_only_after_durable_grant_burn(tmp_path, monkeypatch):
    """Generating before burn would let randomness precede one-use authority."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)
    service = _service(tmp_path, OWNER_A)
    def generate_after_burn():
        with pytest.raises(GrantError) as burned:
            service.grants.consume(grant_ref, request, now=NOW)
        assert burned.value.code == "APPROVAL_EXPIRED"
        return "jrn_11111111111111111111111111111111"
    monkeypatch.setattr(service, "_new_journey_ref", generate_after_burn)
    ack = service.create(
        client_request_id="ordered-create", body=body, grant_ref=grant_ref,
        grant_request=request,
    )
    assert ack.journey_ref == "jrn_11111111111111111111111111111111"


def test_crash_after_durable_burn_requires_new_approval_and_never_mutates(tmp_path):
    """Burning after mutation could replay authority after an interrupted acknowledgement."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)

    class SimulatedCrash(BaseException):
        pass

    def crash(point):
        if point == "after_grant_burn":
            raise SimulatedCrash()

    with pytest.raises(SimulatedCrash):
        _service(tmp_path, OWNER_A, fault_injector=crash).create(
            client_request_id="crash-create", body=body, grant_ref=grant_ref,
            grant_request=request,
        )
    assert _service(tmp_path, OWNER_A).list() == []

    with pytest.raises(GrantError) as burned:
        _service(tmp_path, OWNER_A).create(
            client_request_id="crash-create", body=body, grant_ref=grant_ref,
            grant_request=request,
        )
    assert burned.value.code == str(burned.value) == "APPROVAL_EXPIRED"

    replacement_request = replace(request, nonce="replacement")
    replacement = GrantStore(tmp_path, clock=lambda: NOW).issue(
        replacement_request, approved=True,
    )
    ack = _service(tmp_path, OWNER_A).create(
        client_request_id="crash-create", body=body,
        grant_ref=replacement["grant_ref"], grant_request=replacement_request,
    )
    assert _service(tmp_path, OWNER_A).resume(ack.journey_ref)["journey_ref"] == ack.journey_ref


def test_normal_fault_after_burn_is_a_fixed_non_echo_store_failure(tmp_path):
    """Letting an internal exception escape would expose host detail after authority burned."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)

    def fail(_point):
        raise RuntimeError(r"C:\private\operator\secret")

    with pytest.raises(JourneyStoreError) as failure:
        _service(tmp_path, OWNER_A, fault_injector=fail).create(
            client_request_id="fixed-failure", body=body, grant_ref=grant_ref,
            grant_request=request,
        )
    assert failure.value.code == str(failure.value) == "STORE_COMMIT_FAILED"
    assert "private" not in str(failure.value)


def test_mutating_caller_body_after_authorization_cannot_change_stored_bytes(tmp_path):
    """Passing caller-owned dictionaries through the burn boundary would widen approval."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)

    def mutate(point):
        if point == "after_grant_burn":
            body["goal"] = "tampered after approval"
            body["intake"]["receipt_refs"][0] = "private/tampered.json"

    ack = _service(tmp_path, OWNER_A, fault_injector=mutate).create(
        client_request_id="snapshot-create", body=body, grant_ref=grant_ref,
        grant_request=request,
    )
    event_path = next((
        tmp_path / "journeys" / "v2" / "owners" / OWNER_A / ack.journey_ref / "events"
    ).glob("*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    assert event["payload"]["goal"] == "Preserve exact evidence"
    assert event["payload"]["intake"] == {"receipt_refs": ["evidence/intake.json"]}


def test_empty_request_id_is_rejected_before_grant_burn(tmp_path):
    """Store validation after consume would waste approval on an invalid request key."""
    body = _create_body()
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)
    service = _service(tmp_path, OWNER_A)
    with pytest.raises(ValueError) as failure:
        service.create(
            client_request_id="", body=body, grant_ref=grant_ref,
            grant_request=request,
        )
    assert str(failure.value) == "client_request_id must be a non-empty string"

    ack = service.create(
        client_request_id="valid-after-rejection", body=body,
        grant_ref=grant_ref, grant_request=request,
    )
    assert service.resume(ack.journey_ref)["journey_ref"] == ack.journey_ref


def test_malformed_body_is_non_echoing_and_does_not_burn_grant(tmp_path, monkeypatch):
    """A malformed command must fail before durable one-use authority changes state."""
    body = {"unexpected": r"C:\private\operator\secret"}
    request, grant_ref = _approved_create(tmp_path, OWNER_A, body)
    service = _service(tmp_path, OWNER_A)
    monkeypatch.setattr(service, "_new_journey_ref", lambda: pytest.fail("generated ID"))
    with pytest.raises(ValueError) as failure:
        service.create(
            client_request_id="malformed", body=body, grant_ref=grant_ref,
            grant_request=request,
        )
    assert str(failure.value) == "body has invalid mutation fields"
    assert "private" not in str(failure.value)
    consumed = GrantStore(tmp_path, clock=lambda: NOW).consume(
        grant_ref, request, now=NOW,
    )
    assert consumed["consumed"] is True
