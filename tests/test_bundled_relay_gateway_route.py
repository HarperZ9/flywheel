import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer


def _start_gateway(tmp_path, monkeypatch, token="relay-status-token"):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref

    flywheel_home = tmp_path / "home"
    owner = load_or_create_owner_ref(flywheel_home)
    monkeypatch.setattr(gateway._Handler, "root", tmp_path, raising=False)
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path / "runs"),
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", flywheel_home,
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "auth_token", token, raising=False)
    monkeypatch.setattr(gateway._Handler, "allowed_hosts",
                        gateway.DEFAULT_HOSTS, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return gateway, server, thread, flywheel_home, owner, token


def _post(server, token, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read())


def _journey(state, owner):
    from harness.journey_store import JourneyStore, MutationCommand

    journey_ref = "jrn_" + "b" * 32
    head = JourneyStore(state).create(MutationCommand(
        owner, journey_ref, None, "relay-status-create-1", "intake",
        {"legacy_label": None, "goal": "read relay status", "intake": {},
         "occurred_at": "2026-09-10T12:00:00Z"})).event_head_sha256
    return journey_ref, head


def test_exact_grant_lane_call_reaches_relay_status_once(tmp_path, monkeypatch):
    """Catches bypassing the exact lane.call grant route."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec

    calls = []

    class FakeClient:
        def __init__(self, command, *, timeout, client_name):
            calls.append((command, timeout, client_name))

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def call_text(self, tool, args):
            assert tool == "relay.status"
            assert args == {}
            return {"ok": True, "text": json.dumps({
                "ok": True, "server": "relay", "version": "0.2.0"})}

    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: LaunchSpec(
        ("gateway.exe", "--bundled-lane-mcp", "relay"),
        allowed_tools=("relay.status",)))
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    _gateway, server, thread, home, owner, token = _start_gateway(tmp_path, monkeypatch)
    journey_ref, head = _journey(home / "state", owner)
    operation = {"name": "relay", "tool": "relay.status", "args": {},
                 "governance_tier": "T2", "timeout": 5,
                 "data_refs": [], "credential_refs": []}

    try:
        status, proposal = _post(server, token, "/api/gateway-grants/prepare/lane.call", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "relay-status-http-1",
            "operation": operation,
        })
        assert status == 200, proposal
        status, approval = _post(server, token, "/api/gateway-grants/approve-once", {
            "proposal_ref": proposal["proposal_ref"],
        })
        assert status == 200, approval
        status, payload = _post(server, token, "/api/lane/relay/relay.status", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "relay-status-http-1",
            "grant_ref": approval["grant_ref"],
            **operation,
        })
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status == 200, payload
    assert payload == {"ok": True, "server": "relay", "version": "0.2.0"}
    assert len(calls) == 1
    assert calls[0][0].allowed_tools == ("relay.status",)


def test_direct_relay_lane_post_without_approved_grant_dispatches_zero_times(tmp_path, monkeypatch):
    """Catches direct ungranted lane POST dispatch."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []
    monkeypatch.setattr(lanes, "resolve_mcp_launch",
                        lambda name: calls.append(("resolve", name)) or [])
    monkeypatch.setattr(mcp_client, "MCPClient",
                        lambda *args, **kwargs: calls.append(("client", args)))
    _gateway, server, thread, _home, _owner, token = _start_gateway(tmp_path, monkeypatch)

    try:
        status, payload = _post(server, token, "/api/lane/relay/relay.status", {
            "name": "relay", "tool": "relay.status", "args": {}})
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status in {400, 401, 403, 422}
    assert calls == []
    assert "relay" not in json.dumps(payload).lower()


def test_changed_tool_or_route_after_approval_dispatches_zero_times(tmp_path, monkeypatch):
    """Catches replaying a grant for one Relay tool onto another route."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []
    monkeypatch.setattr(lanes, "resolve_mcp_launch",
                        lambda name: calls.append(("resolve", name)) or [])
    monkeypatch.setattr(mcp_client, "MCPClient",
                        lambda *args, **kwargs: calls.append(("client", args)))
    _gateway, server, thread, home, owner, token = _start_gateway(tmp_path, monkeypatch)
    journey_ref, head = _journey(home / "state", owner)
    operation = {"name": "relay", "tool": "relay.status", "args": {},
                 "governance_tier": "T2", "timeout": 5,
                 "data_refs": [], "credential_refs": []}

    try:
        status, proposal = _post(server, token, "/api/gateway-grants/prepare/lane.call", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "relay-status-http-2",
            "operation": operation,
        })
        assert status == 200, proposal
        status, approval = _post(server, token, "/api/gateway-grants/approve-once", {
            "proposal_ref": proposal["proposal_ref"],
        })
        assert status == 200, approval
        status, payload = _post(server, token, "/api/lane/relay/local_agent_start", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "relay-status-http-2",
            "grant_ref": approval["grant_ref"],
            **operation,
        })
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status in {400, 409, 422}
    assert calls == []
    assert "match" in json.dumps(payload).lower()


def test_approved_suffix_path_rejects_consumes_grant_and_dispatches_zero_times(
        tmp_path, monkeypatch):
    """Catches a non-canonical suffix path using an approved Relay status grant."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    from harness.mcp_client import LaunchSpec

    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append(("client", args, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def call_text(self, tool, args):
            calls.append(("call_text", tool, args))
            return {"ok": True, "text": json.dumps({
                "ok": True, "server": "relay", "version": "0.2.0"})}

    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: LaunchSpec(
        ("gateway.exe", "--bundled-lane-mcp", "relay"),
        allowed_tools=("relay.status",)))
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
    _gateway, server, thread, home, owner, token = _start_gateway(tmp_path, monkeypatch)
    journey_ref, head = _journey(home / "state", owner)
    operation = {"name": "relay", "tool": "relay.status", "args": {},
                 "governance_tier": "T2", "timeout": 5,
                 "data_refs": [], "credential_refs": []}
    request = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": journey_ref,
        "expected_event_head": head,
        "client_request_id": "relay-status-http-suffix",
        "operation": operation,
    }

    try:
        status, proposal = _post(
            server, token, "/api/gateway-grants/prepare/lane.call", request)
        assert status == 200, proposal
        status, approval = _post(server, token, "/api/gateway-grants/approve-once", {
            "proposal_ref": proposal["proposal_ref"],
        })
        assert status == 200, approval
        call_body = {
            "schema": request["schema"],
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": request["client_request_id"],
            "grant_ref": approval["grant_ref"],
            **operation,
        }
        status, payload = _post(
            server, token, "/api/lane/relay/relay.status/extra", call_body)
        retry_status, retry_payload = _post(
            server, token, "/api/lane/relay/relay.status", call_body)
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status == 400, payload
    assert payload["code"] == "GATEWAY_ROUTE_MALFORMED"
    assert "use /api/lane" in payload["error"]
    assert calls == []
    assert retry_status == 403, retry_payload
    assert retry_payload["error"]["code"] == "APPROVAL_EXPIRED"
    assert calls == []


def test_direct_relay_start_proxy_is_not_admitted(tmp_path, monkeypatch):
    """Catches the legacy Relay start proxy becoming an ungated run launcher."""
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []
    monkeypatch.setattr(lanes, "resolve_mcp_launch",
                        lambda name: calls.append(("resolve", name)) or [])
    monkeypatch.setattr(mcp_client, "MCPClient",
                        lambda *args, **kwargs: calls.append(("client", args)))
    _gateway, server, thread, _home, _owner, token = _start_gateway(tmp_path, monkeypatch)

    try:
        status, payload = _post(server, token, "/api/relay/start", {
            "goal": "run a model-backed task", "allow_exec": True})
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status in {400, 403}
    assert payload["code"] == "CAPABILITY_NOT_ADMITTED"
    assert calls == []
