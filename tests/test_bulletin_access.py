from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from harness.gateway_operation import AuthorizedOperation
from harness.lane_caller import call_lane_tool, list_available_lanes
from harness.outcome_bulletin_gateway import dispatch_outcome_bulletin_gateway


def _no_mcp_resolution(monkeypatch):
    import harness.lanes as lanes

    calls = []

    def _resolve(name):
        calls.append(name)
        raise AssertionError("MCP launch should not be resolved")

    monkeypatch.setattr(lanes, "resolve_mcp_launch", _resolve,
                        raising=False)
    return calls


def _assert_bulletin_denied(result, *, requested, ceiling):
    assert result["governance_denied"] is True
    assert result["policy"] == "flywheel.bulletin-access/v1"
    assert result["lane"] == "bulletin"
    assert result["network_attempted"] is False
    assert result["bulletin_access_requested"] == requested
    assert result["bulletin_access_ceiling"] == ceiling
    assert result["bulletin_access"] == "off"
    assert "board" not in json.dumps(result.get("metadata", {})).lower()


def test_operator_off_ceiling_denies_per_call_full_before_mcp_resolution(
        monkeypatch):
    calls = _no_mcp_resolution(monkeypatch)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", "off")

    result = call_lane_tool(
        "bulletin", "board_feed", {}, governance_tier="T1",
        bulletin_access="full")

    _assert_bulletin_denied(result, requested="full", ceiling="off")
    assert calls == []


def test_per_call_off_narrows_full_ceiling_before_mcp_resolution(monkeypatch):
    calls = _no_mcp_resolution(monkeypatch)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", "full")

    result = call_lane_tool(
        "bulletin", "board_feed", {}, governance_tier="T1",
        bulletin_access="off")

    _assert_bulletin_denied(result, requested="off", ceiling="full")
    assert calls == []


@pytest.mark.parametrize(
    ("ceiling", "error"),
    [("metadata", "unsupported_access_mode"), ("unexpected", "invalid_ceiling")])
def test_unsupported_or_invalid_env_ceiling_fails_closed_before_resolution(
        monkeypatch, ceiling, error):
    calls = _no_mcp_resolution(monkeypatch)
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", ceiling)

    result = call_lane_tool("bulletin", "board_feed", {}, governance_tier="T1")

    _assert_bulletin_denied(result, requested="full", ceiling="invalid")
    assert result["policy_error"] == error
    assert calls == []


def test_full_access_still_uses_existing_mcp_path(monkeypatch):
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []

    class FakeClient:
        def __init__(self, command, *, timeout, client_name):
            calls.append((tuple(command), timeout, client_name))
        def __enter__(self):
            return self
        def __exit__(self, *_exc):
            return False
        def call_text(self, tool, args):
            assert tool == "board_feed"
            assert args == {"limit": 1}
            return {"ok": True, "text": '{"ok":true,"posts":[]}'}

    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", "full")
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: ["mcp", name],
                        raising=False)
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)

    result = call_lane_tool(
        "bulletin", "board_feed", {"limit": 1}, governance_tier="T1",
        bulletin_access="full")

    assert result == {"ok": True, "posts": []}
    assert calls == [(('mcp', 'bulletin'), 20, 'flywheel-bulletin-proxy')]


def test_lane_listing_reports_only_sanitized_off_full_policy():
    bulletin = {row["name"]: row for row in list_available_lanes()}["bulletin"]
    policy = bulletin["bulletin_access_policy"]
    assert policy == {
        "schema": "flywheel.bulletin-access-policy/v1",
        "env_ceiling": "FLYWHEEL_BULLETIN_ACCESS",
        "supported_modes": ["off", "full"],
        "metadata_mode": "unsupported",
        "default_ceiling": "full",
    }


@pytest.mark.parametrize("tool", [
    "board_write_post",
    "board_publish_media_post",
])
def test_builtin_bulletin_dispatch_denies_off_before_preview_or_key(
        monkeypatch, tool):
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", "off")
    auth = AuthorizedOperation.for_test(
        action="lane.call",
        operation={
            "name": "bulletin", "tool": tool, "args": {},
            "governance_tier": "T2", "bulletin_access": "full",
            "data_refs": [], "credential_refs": ["cred_" + "a" * 32],
        },
        scopes=("exec", "network", "plugin", "secrets"))

    result, code = dispatch_outcome_bulletin_gateway(auth)

    assert code == 403
    _assert_bulletin_denied(result, requested="full", ceiling="off")
    assert result["tool"] == tool


@pytest.mark.parametrize(("ceiling", "expected_code"), [
    ("off", 403),
    ("full", 200),
])
def test_actual_gateway_lane_route_enforces_access_before_transport(
        tmp_path, monkeypatch, ceiling, expected_code):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref
    from harness.journey_store import JourneyStore, MutationCommand
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client

    calls = []
    journey_ref = "jrn_" + "b" * 32

    class FakeClient:
        def __init__(self, command, *, timeout, client_name):
            calls.append((tuple(command), timeout, client_name))
        def __enter__(self):
            return self
        def __exit__(self, *_exc):
            return False
        def call_text(self, tool, args):
            return {"ok": True, "text": '{"ok":true,"posts":[]}'}

    token = "bulletin-access-token"
    flywheel_home = tmp_path / "home"
    owner = load_or_create_owner_ref(flywheel_home)
    state = flywheel_home / "state"
    head = JourneyStore(state).create(MutationCommand(
        owner, journey_ref, None, "bulletin-access-create-1", "intake",
        {"legacy_label": None, "goal": "read bulletin board", "intake": {},
         "occurred_at": "2026-09-09T12:00:00Z"})).event_head_sha256
    monkeypatch.setenv("FLYWHEEL_BULLETIN_ACCESS", ceiling)
    monkeypatch.setattr(lanes, "resolve_mcp_launch", lambda name: ["mcp", name],
                        raising=False)
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)
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

    def post(path, body):
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

    try:
        operation = {
            "name": "bulletin", "tool": "board_feed", "args": {},
            "governance_tier": "T1", "bulletin_access": "full",
            "data_refs": [], "credential_refs": [],
        }
        status, proposal = post("/api/gateway-grants/prepare/lane.call", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "bulletin-access-http-1",
            "operation": operation,
        })
        assert status == 200, proposal
        assert proposal["operation_sha256"]
        status, approval = post("/api/gateway-grants/approve-once", {
            "proposal_ref": proposal["proposal_ref"],
        })
        assert status == 200, approval
        status, payload = post("/api/lane/bulletin/board_feed", {
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": journey_ref,
            "expected_event_head": head,
            "client_request_id": "bulletin-access-http-1",
            "grant_ref": approval["grant_ref"],
            **operation,
        })
    finally:
        server.shutdown()
        thread.join(2)
        server.server_close()

    assert status == expected_code, payload
    if ceiling == "off":
        _assert_bulletin_denied(payload, requested="full", ceiling="off")
        assert calls == []
    else:
        assert payload == {"ok": True, "posts": []}
        assert calls == [(('mcp', 'bulletin'), 20,
                          'flywheel-bulletin-proxy')]
