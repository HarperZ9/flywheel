"""Actual synthetic HTTP requests exercise the existing gateway auth guards."""
import base64
import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from harness.gateway import _Handler
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import GatewayOperationError

OWNER, JOURNEY, OP = "owner_" + "a" * 32, "jrn_" + "b" * 32, "op_" + "c" * 32
MARKER, TOKEN = "PRIVATE_HTTP_FIXTURE_583ab", "synthetic-http-trace-token"


@pytest.fixture
def server(tmp_path):
    (tmp_path / "owner.ref").write_text(OWNER)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    trace.append("result", {"final": MARKER, "duration_s": 0.001})
    projected = trace.projection("completed")
    def snapshot(owner, op):
        if owner != OWNER or op != OP: raise GatewayOperationError("NOT_FOUND")
        return SimpleNamespace(journey_ref=JOURNEY, state="completed")
    service = SimpleNamespace(state_root=tmp_path, snapshot=snapshot,
        result=lambda *a: {"result": projected})
    class Handler(_Handler):
        auth_token, owner_ref = TOKEN, OWNER
        flywheel_home, root, run_root = tmp_path, tmp_path, tmp_path
        def _operation_components(self): return service, None
        def log_message(self, *_args): pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    def request(query=None, token=TOKEN, host=None):
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        if host: headers["Host"] = host
        conn = HTTPConnection("127.0.0.1", http.server_port, timeout=20)
        try:
            conn.request("GET", "/api/operations/" + OP + "/trace?" + (
                query if query is not None else "ref=" + trace.ref + "&sequence=0"), headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally: conn.close()
    yield Handler, request, trace
    http.shutdown(); http.server_close(); thread.join(20)


@pytest.mark.parametrize("mode", ["off", "missing", "wrong", "host"])
def test_trace_auth_boundary_rejects_before_content_read(server, mode):
    handler, request, _ = server
    if mode == "off": handler.auth_token = None
    status, value = request(token=None if mode in {"off", "missing"} else (
        "wrong" if mode == "wrong" else TOKEN), host="foreign.invalid" if mode == "host" else None)
    assert status == 401 and value["error"]["code"] == "AUTH_REQUIRED"
    assert MARKER not in json.dumps(value)


def test_authenticated_detail_preserves_original_bytes_and_float(server):
    _, request, _ = server
    status, value = request()
    assert status == 200 and value["record"]["payload"]["final"] == MARKER
    canonical = base64.b64decode(value["record_canonical_base64"], validate=True)
    assert hashlib.sha256(canonical).hexdigest() == value["record"]["record_sha256"]
    assert json.loads(canonical)["payload"]["duration_s"] == 0.001
    assert value["next_sequence"] is None


@pytest.mark.parametrize("query", ["ref=../outside&sequence=0", "ref=x&sequence=0",
    "ref=x&ref=y&sequence=0", "ref=x&sequence=-1", "ref=x&sequence=2048"])
def test_malformed_refs_are_typed_without_private_echo(server, query):
    _, request, _ = server
    status, value = request(query)
    assert status == 422 and value["error"]["code"] == "INVALID_REQUEST"
    assert MARKER not in json.dumps(value)


def test_other_owner_and_tampered_terminal_trace_are_not_disclosed(server):
    handler, request, trace = server
    (trace.root / "owner.ref").write_text("owner_" + "d" * 32)
    status, value = request()
    assert status == 404 and MARKER not in json.dumps(value)
    (trace.root / "owner.ref").write_text(OWNER)
    path = trace.root / trace.base / "00000000.json"
    path.write_text(path.read_text().replace(MARKER, "tampered"))
    status, value = request()
    assert status >= 400 and MARKER not in json.dumps(value)
