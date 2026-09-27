"""The two lane setup choices are granted actions, and node.exe is pinned.

Security findings S3 and S6, POLICY-DECISION C-15, correctness C11 and C12:

- ``POST /api/settings/node_path`` and ``POST /api/lanes/local-model/root``
  need an exact grant (``settings.node_path``, ``lane.root``); a bearer token
  alone writes nothing;
- only an absolute path to a file named node.exe is kept, with its sha256, and
  discovery refuses a node.exe that changed since it was chosen;
- a failed ``node --version`` is not cached;
- ``/api/lanes/<lane>/check`` is private;
- a lane whose runtime cannot start answers a grant prepare with a lane code
  from the closed set, not ``LANE_UNAVAILABLE`` (S7).
"""
from __future__ import annotations

import pytest

from harness.gateway_custody import is_private
from harness.gateway_operation import action_for_path, canonicalize_operation
from harness.lane_settings_route import file_sha256, node_path_post
from tests.test_lane_console_route import _journey, _post, _start

REFS = {"data_refs": [], "credential_refs": []}


def test_both_settings_are_granted_actions_with_fixed_scopes():
    assert action_for_path("/api/settings/node_path") == "settings.node_path"
    assert action_for_path("/api/lanes/local-model/root") == "lane.root"
    node = canonicalize_operation("settings.node_path", {**REFS, "path": "C:/n/node.exe"})
    assert node.scopes == ("write", "exec")
    assert dict(node.destination) == {"kind": "setting", "ref": "node_path"}
    root = canonicalize_operation("lane.root", dict(REFS))
    assert root.scopes == ("write",)
    # The desktop reads a ref ending in "/root" as a private path and refuses
    # the proposal, so the folder setting names itself without a slash.
    assert dict(root.destination) == {"kind": "setting", "ref": "local-model-root"}


def test_the_check_route_is_private():
    assert is_private("/api/lanes/bulletin/check")
    assert not is_private("/api/lanes/bulletin/setup")


@pytest.mark.parametrize("given,reason", [("node.exe", "path_not_absolute"),
                                          ("relative/node.exe", "path_not_absolute")])
def test_a_relative_path_is_refused(tmp_path, given, reason):
    body, status = node_path_post({"path": given}, {"FLYWHEEL_HOME": str(tmp_path)},
                                  version_probe=lambda _p: "v22.0.0", platform="nt")
    assert (status, body["reason"]) == (400, reason)
    assert not (tmp_path / "node_path").exists()


@pytest.mark.parametrize("name", ["node.cmd", "node.bat", "node"])
def test_only_node_exe_is_kept_on_windows(tmp_path, name):
    target = tmp_path / name
    target.write_text("@echo off", encoding="utf-8")
    body, status = node_path_post({"path": str(target)}, {"FLYWHEEL_HOME": str(tmp_path)},
                                  version_probe=lambda _p: "v22.0.0", platform="nt")
    assert (status, body["reason"]) == (400, "not_a_node_executable")


def test_a_node_exe_that_changed_since_it_was_chosen_is_not_run(tmp_path):
    from harness.tool_discovery import find_node
    home = tmp_path / "home"
    node = tmp_path / "tools" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"original")
    env = {"FLYWHEEL_HOME": str(home)}
    body, status = node_path_post({"path": str(node)}, env,
                                  version_probe=lambda _p: "v22.0.0", platform="nt")
    assert status == 200
    ran = []
    probe = lambda path: ran.append(path) or "v22.0.0"  # noqa: E731
    found = find_node(env, home=home, node_version=probe, platform="nt",
                      read_registry_path=lambda _s: None)
    assert found.found and found.source == "node_path"
    node.write_bytes(b"replaced by something else")
    ran.clear()
    changed = find_node(env, home=home, node_version=probe, platform="nt",
                        read_registry_path=lambda _s: None)
    assert not changed.found and "changed since it was chosen" in changed.detail
    assert ran == []


def test_a_failed_version_probe_is_tried_again(tmp_path, monkeypatch):
    from harness import tool_discovery as td
    exe = tmp_path / "node.exe"
    exe.write_bytes(b"x")
    answers = iter([None, "v22.0.0"])
    monkeypatch.setattr(td, "_run_version", lambda _path: next(answers))
    assert td.node_version(str(exe)) is None
    assert td.node_version(str(exe)) == "v22.0.0"
    assert td.node_version(str(exe)) == "v22.0.0"   # a success stays cached


def test_file_sha256_matches_hashlib(tmp_path):
    import hashlib
    path = tmp_path / "f"
    path.write_bytes(b"abc")
    assert file_sha256(path) == hashlib.sha256(b"abc").hexdigest()


def test_an_ungranted_post_writes_nothing_and_a_granted_one_does(tmp_path, monkeypatch):
    server, home, owner, token = _start(tmp_path, monkeypatch)
    project = tmp_path / "project"
    project.mkdir()
    ref, head = _journey(home / "state", owner)
    operation = {**REFS, "path": str(project)}
    envelope = {"schema": "flywheel.gateway-operation/v1", "journey_ref": ref,
                "expected_event_head": head, "client_request_id": "lane-root-1"}
    import os
    from harness.lane_workdir import flywheel_home
    # the route writes under the engine's own home, which the test run pins
    root_file = flywheel_home(os.environ) / "lanes" / "local-model" / "root"
    root_file.unlink(missing_ok=True)
    try:
        raw = _post(server, token, "/api/lanes/local-model/root", {"path": str(project)})
        node = _post(server, token, "/api/settings/node_path", {"path": "C:/x/node.exe"})
        written_before = root_file.exists() or (
            flywheel_home(os.environ) / "node_path").exists()
        status, proposal = _post(server, token, "/api/gateway-grants/prepare/lane.root",
                                 {**envelope, "operation": operation})
        assert status == 200, proposal
        status, approval = _post(server, token, "/api/gateway-grants/approve-once",
                                 {"proposal_ref": proposal["proposal_ref"]})
        assert status == 200, approval
        status, body = _post(server, token, "/api/lanes/local-model/root",
                             {**envelope, "grant_ref": approval["grant_ref"], **operation})
    finally:
        server.shutdown()
        server.server_close()
    assert raw[0] in (403, 422) and node[0] in (403, 422), (raw, node)
    assert written_before is False
    assert status == 200 and body["met"] is True, body
    assert root_file.read_text(encoding="utf-8").strip() == str(project)
    root_file.unlink()


def test_a_grant_prepare_for_a_lane_that_cannot_start_names_a_lane_code(monkeypatch):
    from harness import plugins
    from harness.gateway_operation import GatewayOperationError
    import harness.lanes as lanes
    from harness.lane_runtime import LaneRuntimeError

    def blocked(codes):
        def resolve(name):
            raise LaneRuntimeError(name, codes)
        return resolve

    monkeypatch.setattr(plugins, "resolve_mcp_launch", blocked(("local_model_root_unset",)))
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    with pytest.raises(GatewayOperationError, match="LANE_SETUP_REQUIRED"):
        plugins.plugin_execution_plan("local-model")
    monkeypatch.setattr(plugins, "resolve_mcp_launch", blocked(("lane_held",)))
    with pytest.raises(GatewayOperationError, match="LANE_CANNOT_LAUNCH"):
        plugins.plugin_execution_plan("telos")
