import json
from datetime import datetime, timedelta, timezone

import pytest

from gateway_grant_relay_source_fixture import relay_source_runtime  # noqa: F401

import harness.gateway_grant_route as grant_route
import harness.gateway_grant_index as index
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand
from harness.operation_grants import GrantError

NOW = "2026-09-07T12:00:00Z"
OLD = "2026-09-06T10:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _time(offset=0):
    base = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


def _journey(root):
    return JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "create-index", "intake",
        {"legacy_label": None, "goal": "approval index", "intake": {},
         "occurred_at": NOW}))


def _operation(label="write summary"):
    return {"name": "relay", "tool": "relay.run",
            "arguments": {"goal": label, "limit": 2},
            "data_refs": ["data_mobile"], "credential_refs": []}


def _post(root, route, body, *, clock=lambda: NOW):
    return gateway_grant_post(
        f"/api/gateway-grants/{route}", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=root, clock=clock)


def _prepare(root, request, *, clock=lambda: NOW):
    head = JourneyStore(root).load(OWNER, JOURNEY)["event_head_sha256"]
    value, status = _post(root, "prepare/plugin.call", {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": request, "operation": _operation(request)},
        clock=clock)
    assert status == 200, value
    return value


def _list(root, *, state="pending", limit=25, cursor=None, clock=lambda: NOW):
    body = {"schema": "flywheel.gateway-grant-list-request/v1",
            "state": state, "limit": limit, "cursor": cursor}
    return _post(root, "list", body, clock=clock)


def _read(root, proposal, *, clock=lambda: NOW):
    return _post(root, "read", {
        "schema": "flywheel.gateway-grant-read-request/v1",
        "proposal_ref": proposal["proposal_ref"]}, clock=clock)


def _review(root, proposal, *, clock=lambda: NOW):
    value, status = _read(root, proposal, clock=clock)
    assert status == 200, value
    return value["review"]


def _approve(root, proposal, *, clock=lambda: NOW):
    review = _review(root, proposal, clock=clock)
    value, status = _post(root, "approve-reviewed-once", {
        "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
        "proposal_ref": proposal["proposal_ref"],
        "review_sha256": review["review_sha256"]}, clock=clock)
    assert status == 200, value
    return value


def _reject(root, proposal, *, clock=lambda: NOW):
    listed, status = _list(root, limit=1, clock=clock)
    assert status == 200, listed
    item = next(row for row in listed["items"]
                if row["proposal_ref"] == proposal["proposal_ref"])
    value, status = _post(root, "reject", {
        "schema": "flywheel.gateway-grant-reject-request/v1",
        "proposal_ref": item["proposal_ref"],
        "expected_record_sha256": item["record_sha256"]}, clock=clock)
    assert status == 200, value
    return value


def _owner_dir(root):
    return root / "gateway-grant-proposals" / OWNER


def test_list_limit_one_reads_two_index_rows_and_two_records(tmp_path):
    _journey(tmp_path)
    for i in range(75):
        _prepare(tmp_path, f"request-{i:02d}")

    value, status = _list(tmp_path, limit=1)

    assert status == 200, value
    assert len(value["items"]) == 1
    assert value["next_cursor"] is not None
    assert value["index_complete"] is True
    assert value["inspected_index_rows"] == 2
    assert value["record_reads"] == 2


def test_index_cursor_paginates_without_duplicates(tmp_path):
    _journey(tmp_path)
    expected = {_prepare(tmp_path, f"request-{i}")["proposal_ref"]
                for i in range(3)}
    seen, cursor = [], None

    while True:
        value, status = _list(tmp_path, limit=1, cursor=cursor)
        assert status == 200, value
        seen.extend(row["proposal_ref"] for row in value["items"])
        cursor = value["next_cursor"]
        if cursor is None:
            break

    assert set(seen) == expected
    assert len(seen) == len(set(seen)) == 3


def test_decided_recent_has_a_24_hour_window(tmp_path):
    _journey(tmp_path)
    old = _prepare(tmp_path, "old", clock=lambda: OLD)
    new = _prepare(tmp_path, "new")
    _reject(tmp_path, old, clock=lambda: "2026-09-06T10:01:00Z")
    _approve(tmp_path, new)

    value, status = _list(tmp_path, state="decided_recent", limit=10)

    assert status == 200, value
    assert value["decided_recent_window_seconds"] == 24 * 60 * 60
    assert [row["proposal_ref"] for row in value["items"]] == [
        new["proposal_ref"]]


def test_missing_legacy_index_is_explicitly_incomplete(tmp_path):
    _journey(tmp_path)
    proposal = _prepare(tmp_path, "legacy")
    (_owner_dir(tmp_path) / index.INDEX_FILENAME).unlink()

    value, status = _list(tmp_path, limit=1)

    assert status == 200, value
    assert proposal["proposal_ref"] not in [r["proposal_ref"]
                                            for r in value["items"]]
    assert value["index_complete"] is False
    assert value["list_status"] == "legacy_index_required"


def test_missing_index_clutter_is_not_reported_complete(tmp_path):
    owner = _owner_dir(tmp_path)
    owner.mkdir(parents=True)
    for i in range(65):
        (owner / f"noise-{i}.tmp").write_text("x", encoding="utf-8")

    value, status = _list(tmp_path, limit=1)

    assert status == 200, value
    assert value["items"] == []
    assert value["index_complete"] is False
    assert value["list_status"] == "legacy_index_required"


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_failed_decision_write_leaves_lists_incomplete(tmp_path, monkeypatch,
                                                       action):
    _journey(tmp_path)
    proposal = _prepare(tmp_path, f"{action}-crash")

    def fail_write(_path, _value):
        raise OSError("simulated proposal write crash")

    monkeypatch.setattr(grant_route, "_replace", fail_write)
    if action == "approve":
        review = _review(tmp_path, proposal)
        value, status = _post(tmp_path, "approve-reviewed-once", {
            "schema": "flywheel.gateway-grant-reviewed-approval-request/v1",
            "proposal_ref": proposal["proposal_ref"],
            "review_sha256": review["review_sha256"]})
    else:
        listed, status = _list(tmp_path, limit=1)
        assert status == 200, listed
        value, status = _post(tmp_path, "reject", {
            "schema": "flywheel.gateway-grant-reject-request/v1",
            "proposal_ref": proposal["proposal_ref"],
            "expected_record_sha256": listed["items"][0]["record_sha256"]})
    assert status == 500, value

    for state in ("pending", "recoverable"):
        value, status = _list(tmp_path, state=state, limit=10)
        assert status == 200, value
        assert value["index_complete"] is False
        assert value["list_status"] == "index_mutation_pending"
        assert proposal["proposal_ref"] in [r["proposal_ref"]
                                            for r in value["items"]]


def test_index_ahead_of_record_reports_drift_incomplete(tmp_path):
    _journey(tmp_path)
    proposal = _prepare(tmp_path, "crash")
    (_owner_dir(tmp_path) / index.record_filename(
        proposal["proposal_ref"])).unlink()

    value, status = _list(tmp_path, limit=1)

    assert status == 200, value
    assert value["items"] == []
    assert value["index_complete"] is False
    assert value["list_status"] == "index_drift"
    assert value["record_reads"] == 1


def test_record_reader_requests_only_cap_plus_one_bytes(monkeypatch):
    sizes = []

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, size):
            sizes.append(size)
            return b"x" * size

    class FakePath:
        def open(self, mode):
            assert mode == "rb"
            return Stream()

    monkeypatch.setattr(index, "MAX_RECORD_BYTES", 16)
    with pytest.raises(GrantError):
        index.read_limited_json(FakePath())
    assert sizes == [17]


def test_malformed_cursor_timestamp_is_invalid_request(tmp_path):
    _journey(tmp_path)
    _prepare(tmp_path, "cursor")

    value, status = _list(tmp_path, cursor="v1|e|not-a-time|prp_" + "a" * 32)

    assert status == 422
    assert value["error"]["code"] == "INVALID_REQUEST"
