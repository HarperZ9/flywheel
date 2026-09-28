"""The lane console routes.

The tool listing spawns the lane, so it takes the same approval as
``plugin.probe``: a consumed plugin.probe grant naming this lane. It lists
from an unfiltered ``tools/list`` and marks each tool against the policy, so a
tool the launch does not admit shows as ``admitted: false`` rather than
vanishing. The two setup choices refuse what the engine would refuse later.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from harness.gateway_custody import is_private
from harness.lane_console_route import (console_get, node_path_post, parse_console_path,
                                        root_post, tools_listing, tools_post)
from harness.mcp_client import LaunchSpec

SPECS = [{"name": "gather.docs", "description": "catalog", "inputSchema": {
             "type": "object", "properties": {"path": {"type": "string"}}}},
         {"name": "gather.run", "description": "run", "inputSchema": {}},
         {"name": "gather.status", "description": "status", "inputSchema": {}}]


class FakeClient:
    spawned: list = []

    def __init__(self, launch, *, timeout, client_name):
        FakeClient.spawned.append(launch)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def list_all_tools(self):
        return list(SPECS)

    def list_tools(self):
        raise AssertionError("the console must list unfiltered")


LAUNCH = LaunchSpec(("engine.exe", "--bundled-lane-mcp", "gather"),
                    allowed_tools=("gather.docs", "gather.status"))


def _runtime(codes=()):
    return SimpleNamespace(blocking_codes=tuple(codes), launch=None if codes else LAUNCH)


def test_unfiltered_listing_marks_what_the_launch_does_not_admit():
    FakeClient.spawned = []
    body, status = tools_listing("gather", LAUNCH, client_factory=FakeClient)
    assert status == 200 and body["schema"] == "flywheel.lane-tools/v1"
    rows = {row["name"]: row for row in body["tools"]}
    assert rows["gather.docs"]["admitted"] is True and rows["gather.docs"]["main"] is True
    assert rows["gather.docs"]["inputSchema"]["properties"]["path"]["type"] == "string"
    assert rows["gather.run"]["admitted"] is False and rows["gather.run"]["tier"] == "T2"
    assert rows["gather.status"]["admitted"] is True


def test_each_row_names_the_arguments_the_desktop_may_fill_with_a_local_path():
    # The desktop keeps local paths out of an operation unless the field is
    # declared to carry one; for a lane tool, the policy's path_args declare it.
    body, _ = tools_listing("gather", LAUNCH, client_factory=FakeClient)
    rows = {row["name"]: row for row in body["tools"]}
    assert rows["gather.docs"]["path_args"] == ["path"]
    assert rows["gather.status"]["path_args"] == []


def test_not_in_build_tools_are_listed_disabled_with_their_reason():
    body, _ = tools_listing("calibrate-pro", LaunchSpec(("x",), allowed_tools=(
        "calibrate-pro.list-panels",)), client_factory=FakeClient)
    targets = next(row for row in body["tools"]
                   if row["name"] == "calibrate-pro.list-targets")
    assert targets["listed"] is False and targets["admitted"] is False
    assert targets["not_in_build"] == "numpy_not_in_build"


def test_listing_failures_are_fixed_codes():
    from harness.mcp_client import MCPError

    def failing(error):
        class Client(FakeClient):
            def __enter__(self):
                raise error
        return Client

    body, status = tools_listing("gather", LAUNCH,
                                 client_factory=failing(MCPError("no response within 20s")))
    assert (status, body["code"], body["timeout_s"]) == (504, "LANE_TIMEOUT", 20)
    body, status = tools_listing("gather", LAUNCH,
                                 client_factory=failing(FileNotFoundError("engine.exe")))
    assert (status, body["code"], body["reason"]) == (
        503, "LANE_CANNOT_LAUNCH", "runtime_executable_missing")
    assert "engine.exe" not in json.dumps(body)


def test_setup_required_refuses_before_the_grant_is_consumed(monkeypatch):
    import harness.lanes as lanes
    monkeypatch.setattr(lanes, "resolve_lane_runtime",
                        lambda name: _runtime(("node_runtime_missing",)))
    consumed = []
    body, status = tools_post("learn", lambda: consumed.append(1))
    assert (status, body["code"], body["setup"]) == (409, "LANE_SETUP_REQUIRED", ["node"])
    assert consumed == []


def test_a_grant_for_another_lane_is_a_mismatch(monkeypatch):
    import harness.lanes as lanes
    monkeypatch.setattr(lanes, "resolve_lane_runtime", lambda name: _runtime())
    other = SimpleNamespace(operation={"name": "crucible"}, execution_plan=None)
    body, status = tools_post("gather", lambda: other, client_factory=FakeClient)
    assert (status, body["code"]) == (409, "GATEWAY_ROUTE_MISMATCH")


def test_paths_and_custody():
    assert parse_console_path("/api/lanes/gather/tools") == ("gather", "tools")
    assert parse_console_path("/api/lanes/gather") is None
    assert is_private("/api/lanes/gather/tools")
    assert is_private("/api/lanes/local-model/root")
    assert is_private("/api/settings/node_path")
    assert not is_private("/api/lanes/gather/setup")
    assert not is_private("/api/lanes/callable")


def test_setup_route_answers_for_a_lane_and_refuses_an_unknown_one(tmp_path):
    env = {"FLYWHEEL_HOME": str(tmp_path), "FLYWHEEL_GIT": "none"}
    body, status = console_get("/api/lanes/index/setup", environ=env)
    assert status == 200 and body["unmet"] == ["git"]
    assert console_get("/api/lanes/nope/setup", environ=env)[1] == 404
    body, status = console_get("/api/lanes/local-model/root", environ=env)
    assert status == 200 and body["id"] == "project_folder" and body["met"] is False


def test_local_model_root_refuses_the_flywheel_home_and_accepts_a_project(tmp_path):
    home = tmp_path / "home"
    (home / "inside").mkdir(parents=True)
    env = {"FLYWHEEL_HOME": str(home)}
    body, status = root_post({"path": str(home / "inside")}, env)
    assert (status, body["reason"]) == (409, "local_model_root_protected")
    body, status = root_post({"path": str(tmp_path / "missing")}, env)
    assert (status, body["reason"]) == (400, "local_model_root_missing")
    project = tmp_path / "project"
    project.mkdir()
    body, status = root_post({"path": str(project)}, env)
    assert status == 200 and body["met"] is True
    body, status = root_post({"path": ""}, env)
    assert status == 200 and body["met"] is False


def test_node_path_runs_only_a_file_named_node_at_version_20(tmp_path):
    env = {"FLYWHEEL_HOME": str(tmp_path / "home")}
    ran = []
    probe = lambda path: ran.append(path) or "v22.3.0"  # noqa: E731
    other = tmp_path / "evil.exe"
    other.write_text("x", encoding="utf-8")
    body, status = node_path_post({"path": str(other)}, env, version_probe=probe,
                                  platform="nt")
    assert (status, body["reason"], ran) == (400, "not_a_node_executable", [])
    node = tmp_path / "node.exe"
    node.write_text("x", encoding="utf-8")
    body, status = node_path_post({"path": str(node)}, env,
                                  version_probe=lambda _p: "v18.0.0", platform="nt")
    assert (status, body["reason"]) == (400, "node_too_old_or_silent")
    body, status = node_path_post({"path": str(node)}, env, version_probe=probe,
                                  platform="nt")
    assert status == 200 and ran == [str(node.resolve())]
    saved = (tmp_path / "home" / "node_path").read_text(encoding="utf-8").splitlines()
    assert saved[0] == str(node.resolve()) and saved[1].startswith("sha256=")
    body, status = node_path_post({"path": None}, env)
    assert status == 200 and not (tmp_path / "home" / "node_path").exists()


# ---- through the gateway, with a real plugin.probe grant ------------------

def _start(tmp_path, monkeypatch, token="lane-console-token"):
    from harness import gateway
    from harness.gateway_auth import load_or_create_owner_ref
    home = tmp_path / "home"
    owner = load_or_create_owner_ref(home)
    for name, value in (("root", tmp_path), ("run_root", str(tmp_path / "runs")),
                        ("flywheel_home", home), ("auth_token", token),
                        ("allowed_hosts", gateway.DEFAULT_HOSTS)):
        monkeypatch.setattr(gateway._Handler, name, value, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), gateway._Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, home, owner, token


def _post(server, token, path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read())


def _journey(state, owner):
    from harness.journey_store import JourneyStore, MutationCommand
    ref = "jrn_" + "c" * 32
    head = JourneyStore(state).create(MutationCommand(
        owner, ref, None, "lane-console-create-1", "intake",
        {"legacy_label": None, "goal": "list gather tools", "intake": {},
         "occurred_at": "2026-09-26T12:00:00Z"})).event_head_sha256
    return ref, head


@pytest.fixture
def patched(monkeypatch):
    import harness.lanes as lanes
    import harness.mcp_client as mcp_client
    import harness.plugins as plugins
    FakeClient.spawned = []
    monkeypatch.setattr(plugins, "resolve_mcp_launch", lambda name: LAUNCH)
    monkeypatch.setattr(lanes, "resolve_lane_runtime", lambda name: _runtime())
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)


def test_listing_takes_the_same_approval_as_plugin_probe(tmp_path, monkeypatch, patched):
    server, home, owner, token = _start(tmp_path, monkeypatch)
    ref, head = _journey(home / "state", owner)
    operation = {"name": "gather", "data_refs": [], "credential_refs": []}
    envelope = {"schema": "flywheel.gateway-operation/v1", "journey_ref": ref,
                "expected_event_head": head, "client_request_id": "lane-tools-1"}
    try:
        denied = _post(server, token, "/api/lanes/gather/tools", {**envelope, **operation})
        assert FakeClient.spawned == []
        status, proposal = _post(server, token, "/api/gateway-grants/prepare/plugin.probe",
                                 {**envelope, "operation": operation})
        assert status == 200, proposal
        status, approval = _post(server, token, "/api/gateway-grants/approve-once",
                                 {"proposal_ref": proposal["proposal_ref"]})
        assert status == 200, approval
        status, body = _post(server, token, "/api/lanes/gather/tools",
                             {**envelope, "grant_ref": approval["grant_ref"], **operation})
        replay = _post(server, token, "/api/lanes/gather/tools",
                       {**envelope, "grant_ref": approval["grant_ref"], **operation})
    finally:
        server.shutdown()
        server.server_close()
    assert denied[0] in (403, 422), denied
    assert status == 200, body
    assert {row["name"]: row["admitted"] for row in body["tools"]}["gather.run"] is False
    assert len(FakeClient.spawned) == 1
    assert replay[0] in (403, 409, 422), replay


def test_listing_needs_the_bearer_token(tmp_path, monkeypatch, patched):
    server, _home, _owner, token = _start(tmp_path, monkeypatch)
    try:
        status, body = _post(server, "wrong-token", "/api/lanes/gather/tools", {})
    finally:
        server.shutdown()
        server.server_close()
    assert status == 401 and body["error"]["code"] == "AUTH_REQUIRED"
    assert FakeClient.spawned == []
