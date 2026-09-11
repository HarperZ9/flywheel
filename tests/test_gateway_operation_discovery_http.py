"""Real HTTP discovery must cross the existing token and host guards."""
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from harness.gateway import _Handler
from harness.gateway_operations import GatewayOperations
from test_gateway_operation_discovery import OWNER, JOURNEY, NOW, PRIVATE, create, queue

TOKEN = "synthetic-operation-discovery-token"


@pytest.fixture
def server(tmp_path):
    (tmp_path / "owner.ref").write_text(OWNER)
    root = tmp_path / "state"
    create(root)
    ref, _ = queue(root, "http-task")
    service = GatewayOperations(root, clock=lambda: NOW)

    class Handler(_Handler):
        auth_token, owner_ref = TOKEN, OWNER
        flywheel_home, root, run_root = tmp_path, tmp_path, tmp_path
        def _operation_components(self): return service, None
        def log_message(self, *_args): pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()

    def request(token=TOKEN, host=None, method="GET"):
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        if host: headers["Host"] = host
        conn = HTTPConnection("127.0.0.1", http.server_port, timeout=10)
        try:
            conn.request(method, "/api/operations?journey_ref=" + JOURNEY, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    yield Handler, request, ref
    http.shutdown()
    http.server_close()
    thread.join(10)


@pytest.mark.parametrize("mode", ["off", "missing", "wrong", "host"])
def test_discovery_rejects_before_reading_private_store(server, mode):
    handler, request, _ = server
    if mode == "off": handler.auth_token = None
    status, value = request(token=None if mode in {"off", "missing"} else (
        "wrong" if mode == "wrong" else TOKEN), host="foreign.invalid" if mode == "host" else None)
    assert status == 401 and value["error"]["code"] == "AUTH_REQUIRED"
    assert PRIVATE not in json.dumps(value)


def test_authenticated_http_route_returns_operation_locator_without_input(server):
    _, request, ref = server
    status, value = request()
    assert status == 200 and value["operations"][0]["operation_ref"] == ref
    assert PRIVATE not in json.dumps(value)


def test_mutating_method_without_origin_is_rejected_by_auth_guard(server):
    _, request, _ = server
    status, value = request(method="DELETE")
    assert status == 401 and value["error"]["code"] == "AUTH_REQUIRED"


def test_discovery_openapi_entry_requires_bearer_auth():
    from harness.discovery_route import openapi_document
    entry = openapi_document()["paths"]["/api/operations"]["get"]
    assert entry["security"] == [{"bearerAuth": []}]


def test_discovery_openapi_does_not_advertise_mutating_methods():
    from harness.discovery_route import openapi_document
    entry = openapi_document()["paths"]["/api/operations"]
    assert set(entry) & {"get", "post", "put", "delete", "head", "patch"} == {"get"}
