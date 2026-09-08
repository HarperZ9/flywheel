import json, sqlite3

from harness.gateway_grant_index import INDEX_FILENAME, read_limited_json, record_filename
from harness.gateway_grant_index_reconcile import reconcile_owner_index
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-09-07T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _journey(root):
    return JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "create-reconcile", "intake",
        {"legacy_label": None, "goal": "reconcile index", "intake": {},
         "occurred_at": NOW}))


def _post(root, route, body, *, clock=lambda: NOW):
    return gateway_grant_post(
        f"/api/gateway-grants/{route}", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=root, clock=clock)


def _prepare(root, request):
    head = JourneyStore(root).load(OWNER, JOURNEY)["event_head_sha256"]
    value, status = _post(root, "prepare/plugin.call", {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": request,
        "operation": {"name": "relay", "tool": "relay.run",
                      "arguments": {"goal": request},
                      "data_refs": ["data_mobile"],
                      "credential_refs": []}})
    assert status == 200, value
    return value


def _list(root):
    value, status = _post(root, "list", {
        "schema": "flywheel.gateway-grant-list-request/v1",
        "state": "pending", "limit": 10, "cursor": None})
    assert status == 200, value
    return value


def _owner_dir(root):
    return root / "gateway-grant-proposals" / OWNER


def _proposal_path(root, proposal):
    return _owner_dir(root) / record_filename(proposal["proposal_ref"])


def _index_sql(root, sql, params=()):
    conn = sqlite3.connect(_owner_dir(root) / INDEX_FILENAME)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.commit()
        conn.close()


def _refs(value):
    return {row["proposal_ref"] for row in value["items"]}


def test_reconcile_repairs_deleted_and_wrong_state_index_rows(tmp_path):
    _journey(tmp_path)
    deleted = _prepare(tmp_path, "deleted-row")
    wrong_state = _prepare(tmp_path, "wrong-state")
    _index_sql(tmp_path, "DELETE FROM proposal_index WHERE proposal_ref=?",
               (deleted["proposal_ref"],))
    _index_sql(tmp_path, "UPDATE proposal_index SET proposal_state='rejected' WHERE proposal_ref=?",
               (wrong_state["proposal_ref"],))
    before = read_limited_json(_proposal_path(tmp_path, wrong_state))

    result = reconcile_owner_index(tmp_path, OWNER, limit=10, now_text=NOW)
    listed = _list(tmp_path)
    after = read_limited_json(_proposal_path(tmp_path, wrong_state))

    assert result["complete"] is True, result
    assert result["records_indexed"] == 2
    assert _refs(listed) == {deleted["proposal_ref"], wrong_state["proposal_ref"]}
    assert listed["coverage_scope"] == "maintained_index"
    assert listed["recovery_required"] is None
    assert before["state"] == after["state"] == "prepared"


def test_reconcile_limit_preserves_old_index_and_marks_recovery(tmp_path):
    _journey(tmp_path)
    missing = _prepare(tmp_path, "missing")
    _prepare(tmp_path, "present")
    _index_sql(tmp_path, "DELETE FROM proposal_index WHERE proposal_ref=?",
               (missing["proposal_ref"],))

    result = reconcile_owner_index(tmp_path, OWNER, limit=1, now_text=NOW)
    listed = _list(tmp_path)

    assert result["complete"] is False
    assert result["recovery_required"] == "SCAN_LIMIT_EXCEEDED"
    assert _index_sql(tmp_path,
                      "SELECT proposal_ref FROM proposal_index WHERE proposal_ref=?",
                      (missing["proposal_ref"],)) == []
    assert listed["index_complete"] is False
    assert listed["list_status"] == "recovery_required"
    assert listed["recovery_required"] == "SCAN_LIMIT_EXCEEDED"


def test_corrupt_source_cannot_clear_recovery_required(tmp_path):
    _journey(tmp_path)
    proposal = _prepare(tmp_path, "corrupt-source")
    _proposal_path(tmp_path, proposal).write_bytes(b"{not-json")

    result = reconcile_owner_index(tmp_path, OWNER, limit=10, now_text=NOW)
    listed = _list(tmp_path)

    assert result["complete"] is False
    assert result["recovery_required"] == "SOURCE_RECORD_INVALID"
    assert listed["index_complete"] is False
    assert listed["recovery_required"] == "SOURCE_RECORD_INVALID"
