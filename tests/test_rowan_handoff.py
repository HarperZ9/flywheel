"""A Rowan run exports as a brief another agent can pick up, owner only."""
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from harness.gateway import _Handler
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError
from harness.rowan_handoff import handoff_markdown
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION
from tests.test_run_completion import WRITE, _run

TOKEN = "synthetic-handoff-token"


def _brief(tmp_path, state, reason=None):
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    records = trace.read()
    projection = trace.projection(state, reason=reason)
    return handoff_markdown(records, projection), records


def test_the_brief_carries_goal_marks_open_items_and_receipts(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, [WRITE, "Created notes.md. Everything works now."])
    brief, records = _brief(tmp_path, "completed")
    assert brief.startswith("# Handoff: write notes")
    assert "- notes.md: verified (file_hash_recheck, matches)" in brief
    assert "- Final answer: claimed (no check, no_check_ran)" in brief
    assert "- Check the final answer: it is claimed and nothing verified it." in brief
    assert "no check backs that claim" in brief
    assert "> Created notes.md. Everything works now." in brief
    assert records[-1]["record_sha256"] in brief
    assert "Completion: claimed. Verified 1, claimed 1, failed 0." in brief


def test_a_stopped_run_says_where_to_pick_up(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, [WRITE], run_budget={"max_tool_actions": 1})
    brief, _ = _brief(tmp_path, "failed", "AGENT_RUN_BUDGET_EXHAUSTED")
    assert "Run state: failed (AGENT_RUN_BUDGET_EXHAUSTED)" in brief
    assert "Budget: stopped on tool_actions." in brief
    assert "The run did not finish (AGENT_RUN_BUDGET_EXHAUSTED)" in brief
    assert "No final answer was recorded." in brief
    assert "Done" not in brief


@pytest.fixture
def server(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, [WRITE, "Created notes.md."])
    (tmp_path / "owner.ref").write_text(OWNER)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    trace.read()
    projected = {"result": trace.projection("completed")}

    def snapshot(owner, op):
        if owner != OWNER or op != OPERATION:
            raise GatewayOperationError("NOT_FOUND")
        return SimpleNamespace(journey_ref=JOURNEY, state="completed")
    service = SimpleNamespace(state_root=tmp_path, snapshot=snapshot,
                              result=lambda *a: projected)

    class Handler(_Handler):
        auth_token, owner_ref = TOKEN, OWNER
        flywheel_home, root, run_root = tmp_path, tmp_path, tmp_path

        def _operation_components(self):
            return service, None

        def log_message(self, *_args):
            pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def request(token=TOKEN, path="/handoff"):
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        conn = HTTPConnection("127.0.0.1", http.server_port, timeout=20)
        try:
            conn.request("GET", "/api/operations/" + OPERATION + path, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()
    yield request, projected
    http.shutdown()
    http.server_close()
    thread.join(20)


def test_the_owner_reads_the_brief_over_http(server):
    request, _ = server
    status, value = request()
    assert status == 200, value
    assert value["schema"] == "flywheel.rowan-handoff/v1"
    assert "notes.md" in value["markdown"]
    assert value["record_count"] > 0 and "NOT_RE_VERIFIED_AT_EXPORT" in value["does_not_prove"]


def test_no_token_no_brief(server):
    request, _ = server
    status, value = request(token=None)
    assert status == 401 and "notes.md" not in json.dumps(value)


def test_a_brief_is_refused_when_the_trace_no_longer_matches_its_result(server):
    request, projected = server
    projected["result"] = {**projected["result"], "record_count": 1}
    status, value = request()
    assert status == 404 and "notes.md" not in json.dumps(value)
