"""Discovery reads real durable Journeys, without running a model or worker."""
from dataclasses import replace
import json
from urllib.parse import urlencode

import pytest

from harness.gateway_operation_route import operation_ref_for, queued_payload, route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.gateway_operation import AuthorizedOperation
from harness.gateway_provider_adapter import ExecutionPlan
from harness.journey_store import JourneyStore, MutationCommand

OWNER, OTHER = "owner_" + "a" * 32, "owner_" + "b" * 32
JOURNEY, SECOND = "jrn_" + "a" * 32, "jrn_" + "b" * 32
NOW, PRIVATE = "2026-09-10T12:00:00Z", "PRIVATE_DISCOVERY_FIXTURE_8793"


def create(root, owner=OWNER, journey=JOURNEY):
    return JourneyStore(root).create(MutationCommand(
        owner, journey, None, "genesis", "intake",
        {"legacy_label": None, "goal": PRIVATE, "intake": {}, "occurred_at": NOW}))


def queue(root, request, owner=OWNER, journey=JOURNEY):
    store = JourneyStore(root)
    authorized = replace(AuthorizedOperation.for_test(action="agent.run", operation={
        "goal": PRIVATE, "endpoint": "stub", "max_steps": 1, "allow_write": False,
        "allow_exec": False, "stream": True, "data_refs": [], "credential_refs": []},
        scopes=("network",)), owner_ref=owner,
                         journey_ref=journey, client_request_id=request,
                         execution_plan=ExecutionPlan("c" * 64, (), ()))
    ack = store.append(MutationCommand(owner, journey,
        store.load(owner, journey)["event_head_sha256"], request, "operation_queued",
        {"occurred_at": NOW, "payload": queued_payload(authorized)}))
    return operation_ref_for(owner, journey, request), ack


def listing(root, owner=OWNER, journey=JOURNEY, **query):
    return route_gateway_operation("GET", "/api/operations", owner_ref=owner,
        query=urlencode({"journey_ref": journey, **query}),
        service=GatewayOperations(root, clock=lambda: NOW), process_factory=None)


def test_lists_only_selected_journey_metadata_newest_first(tmp_path):
    create(tmp_path)
    create(tmp_path, journey=SECOND)
    first, _ = queue(tmp_path, "first")
    second, _ = queue(tmp_path, PRIVATE)
    excluded, _ = queue(tmp_path, "other", journey=SECOND)
    result = listing(tmp_path)
    assert result.status == 200
    assert set(result.body) == {"schema", "journey_ref", "event_head_sha256",
                               "operations", "next_cursor", "request_sha256_by_operation"}
    rows = result.body["operations"]
    assert [r["operation_ref"] for r in rows] == [second, first]
    assert result.body["next_cursor"] is None
    assert rows[0]["state"] == "queued" and rows[0]["can_cancel"] is False
    assert set(rows[0]) == {"schema", "operation_ref", "journey_ref",
        "event_head_sha256", "state", "can_cancel", "terminal_event_ref", "result_sha256"}
    assert PRIVATE not in json.dumps(result.body) and excluded not in json.dumps(result.body)


def test_discovery_correlates_lost_start_response_without_exposing_request_id(tmp_path):
    import hashlib
    create(tmp_path)
    ref, _ = queue(tmp_path, PRIVATE)
    result = listing(tmp_path)
    assert result.status == 200
    assert result.body["request_sha256_by_operation"] == {
        ref: hashlib.sha256(('"' + PRIVATE + '"').encode()).hexdigest()}
    assert PRIVATE not in json.dumps(result.body)


def test_cursor_stays_on_original_head_after_append(tmp_path):
    create(tmp_path)
    first, _ = queue(tmp_path, "first")
    second, _ = queue(tmp_path, "second")
    page = listing(tmp_path, limit=1)
    assert page.status == 200
    assert page.body["operations"][0]["operation_ref"] == second
    newest, _ = queue(tmp_path, "newest")
    tail = listing(tmp_path, limit=1, cursor=page.body["next_cursor"])
    assert tail.status == 200
    assert [r["operation_ref"] for r in tail.body["operations"]] == [first]
    assert tail.body["event_head_sha256"] == page.body["event_head_sha256"]
    assert tail.body["next_cursor"] is None
    assert listing(tmp_path).body["operations"][0]["operation_ref"] == newest


def test_foreign_owner_missing_journey_and_cursor_binding_fail_closed(tmp_path):
    create(tmp_path)
    create(tmp_path, journey=SECOND)
    queue(tmp_path, "first")
    queue(tmp_path, "second")
    assert listing(tmp_path, owner=OTHER).status == 404
    assert listing(tmp_path, journey="jrn_" + "c" * 32).status == 404
    page = listing(tmp_path, limit=1)
    assert page.status == 200
    assert listing(tmp_path, journey=SECOND, cursor=page.body["next_cursor"]).status == 422
    create(tmp_path, owner=OTHER)
    assert listing(tmp_path, owner=OTHER, cursor=page.body["next_cursor"]).status == 422


@pytest.mark.parametrize("query", ["", "journey_ref=../private", "journey_ref=x&journey_ref=y",
    f"journey_ref={JOURNEY}&limit=0", f"journey_ref={JOURNEY}&limit=51",
    f"journey_ref={JOURNEY}&owner_ref={OTHER}", f"journey_ref={JOURNEY}&cursor=bad"])
def test_invalid_queries_never_echo_values(tmp_path, query):
    response = route_gateway_operation("GET", "/api/operations", owner_ref=OWNER,
        query=query, service=GatewayOperations(tmp_path, clock=lambda: NOW), process_factory=None)
    assert response.status == 422
    assert response.body["error"]["code"] == "INVALID_REQUEST"
    assert "../private" not in json.dumps(response.body)


def test_corrupt_committed_event_is_not_a_partial_success(tmp_path):
    create(tmp_path)
    queue(tmp_path, "first")
    event = next((tmp_path / "journeys/v2/owners" / OWNER / JOURNEY / "events").glob("00000000000000000001-*.json"))
    value = json.loads(event.read_bytes())
    value["payload"]["client_request_id"] = PRIVATE
    event.write_text(json.dumps(value))
    result = listing(tmp_path)
    assert result.status == 500 and result.body["error"]["code"] == "STORE_COMMIT_FAILED"
    assert PRIVATE not in json.dumps(result.body)


def test_empty_owned_journey_is_success_and_missing_read_creates_nothing(tmp_path):
    response = listing(tmp_path)
    assert response.status == 404
    assert list(tmp_path.iterdir()) == []
    create(tmp_path)
    response = listing(tmp_path)
    assert response.status == 200 and response.body["operations"] == []


def test_terminal_locator_uses_durable_seal_without_reading_private_result(tmp_path):
    from harness.gateway_operation_process import WorkerOutcome
    create(tmp_path)
    ref, _ = queue(tmp_path, "failed")
    service = GatewayOperations(tmp_path, clock=lambda: NOW)
    terminal = service._terminal(OWNER, ref, WorkerOutcome(
        "failed", {"reason": "EXTERNAL_ACTION_FAILED", "private_detail": PRIVATE}))
    result = listing(tmp_path)
    assert result.status == 200
    row = result.body["operations"][0]
    assert row["state"] == "failed"
    assert row["result_sha256"] == terminal.result_sha256
    assert row["terminal_event_ref"] == terminal.terminal_event_ref
    assert PRIVATE not in json.dumps(result.body)


@pytest.mark.parametrize("limit_name,limit", [("MAX_EVENTS", 1), ("MAX_TOTAL_BYTES", 16)])
def test_history_limits_fail_closed_before_partial_listing(tmp_path, monkeypatch, limit_name, limit):
    import harness.gateway_operation_discovery as discovery
    create(tmp_path)
    queue(tmp_path, "bounded")
    monkeypatch.setattr(discovery, limit_name, limit)
    result = listing(tmp_path)
    assert result.status == 500 and "operations" not in result.body


def test_oversized_head_and_event_are_rejected_without_echo(tmp_path):
    create(tmp_path)
    queue(tmp_path, "bounded")
    directory = tmp_path / "journeys/v2/owners" / OWNER / JOURNEY
    event = next((directory / "events").glob("00000000000000000001-*.json"))
    event.write_bytes(b" " * 1048577)
    assert listing(tmp_path).status == 500
    (directory / "head.json").write_bytes(b" " * 4097)
    assert listing(tmp_path).status == 500


def test_foreign_owner_chain_cannot_be_transplanted_into_selected_owner(tmp_path):
    import shutil
    create(tmp_path, owner=OTHER)
    queue(tmp_path, "foreign", owner=OTHER)
    base = tmp_path / "journeys/v2/owners"
    shutil.copytree(base / OTHER / JOURNEY, base / OWNER / JOURNEY)
    result = listing(tmp_path)
    assert result.status == 500 and "operations" not in result.body


def test_symlinked_journey_is_not_followed(tmp_path):
    import os
    create(tmp_path)
    queue(tmp_path, "linked")
    directory = tmp_path / "journeys/v2/owners" / OWNER / JOURNEY
    saved = directory.with_name("saved")
    directory.rename(saved)
    try:
        os.symlink(saved, directory, target_is_directory=True)
    except OSError:
        saved.rename(directory)
        pytest.skip("Creating a symlink is unavailable on this host")
    result = listing(tmp_path)
    assert result.status == 500 and "operations" not in result.body


def test_cursor_cannot_name_an_uncommitted_or_wrong_head(tmp_path):
    import base64
    create(tmp_path)
    queue(tmp_path, "first")
    queue(tmp_path, "second")
    cursor = listing(tmp_path, limit=1).body["next_cursor"]
    value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    value["head"] = "f" * 64
    forged = base64.urlsafe_b64encode(json.dumps(value, sort_keys=True,
        separators=(",", ":")).encode()).decode().rstrip("=")
    assert listing(tmp_path, cursor=forged).status == 422
