"""local_agent_run takes its write, exec and root authority from the operator.

The stdio MCP server used to read allow_write, allow_exec and root straight from
the tool arguments, which the model writes. A model could grant itself exec, or
point the file tools at a directory outside the workspace. These tests pin the
contract: grants come from server start configuration, a model argument can only
narrow them, and root must resolve (symlinks and .. included) inside the
permitted workspace. Every refusal happens before any agent step runs.
"""
from __future__ import annotations

import json
import os

import pytest

import harness.local_mcp as local_mcp

GRANT_ENV = ("FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE", "FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC",
             "FLYWHEEL_LOCAL_AGENT_WORKSPACE")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    (root / "sub").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    for name in GRANT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(root))
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def runs(monkeypatch):
    seen = []

    def fake_run_agent(agent, goal, executor, ledger, **kwargs):
        seen.append(executor)
        return {"final": "done", "steps": 0, "verified": True, "checkpoint": "0" * 64}

    monkeypatch.setattr(local_mcp, "run_agent", fake_run_agent)
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    return seen


def _run(arguments: dict) -> dict:
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "local_agent_run",
                                            "arguments": arguments}})
    return response["result"]


def _error_code(result: dict) -> str:
    assert result.get("isError") is True, result
    return json.loads(result["content"][0]["text"])["error"]["code"]


def _junction_or_symlink(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return
    pytest.skip("cannot create a directory link on this host")


def test_model_cannot_grant_itself_exec(workspace, runs):
    result = _run({"goal": "run the build", "allow_exec": True})
    assert _error_code(result) == "GRANT_NOT_OPERATOR_APPROVED"
    assert runs == []


def test_model_cannot_grant_itself_write(workspace, runs):
    result = _run({"goal": "edit files", "allow_write": True})
    assert _error_code(result) == "GRANT_NOT_OPERATOR_APPROVED"
    assert runs == []


def test_string_false_is_not_read_as_a_grant(workspace, runs):
    result = _run({"goal": "x", "allow_exec": "false"})
    assert _error_code(result) == "INVALID_GRANT_ARGUMENT"
    assert runs == []


def test_root_outside_workspace_is_refused(workspace, runs):
    result = _run({"goal": "x", "root": str(workspace.parent / "outside")})
    assert _error_code(result) == "ROOT_OUTSIDE_WORKSPACE"
    assert runs == []


def test_relative_dotdot_escape_is_refused(workspace, runs):
    result = _run({"goal": "x", "root": "sub/../../outside"})
    assert _error_code(result) == "ROOT_OUTSIDE_WORKSPACE"
    assert runs == []


def test_symlink_escape_is_refused(workspace, runs):
    _junction_or_symlink(workspace / "link", workspace.parent / "outside")
    result = _run({"goal": "x", "root": "link"})
    assert _error_code(result) == "ROOT_OUTSIDE_WORKSPACE"
    assert runs == []


def test_default_run_has_no_write_or_exec_and_stays_in_workspace(workspace, runs):
    result = _run({"goal": "look around"})
    assert not result.get("isError"), result
    (executor,) = runs
    assert executor.gate.allow_write is False
    assert executor.gate.allow_exec is False
    assert os.path.normcase(executor.root) == os.path.normcase(os.path.realpath(workspace))


def test_operator_grant_applies_and_root_may_narrow_inside(workspace, runs, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE", "1")
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", "1")
    result = _run({"goal": "fix it", "root": "sub"})
    assert not result.get("isError"), result
    (executor,) = runs
    assert executor.gate.allow_write is True
    assert executor.gate.allow_exec is True
    assert os.path.normcase(executor.root) == os.path.normcase(
        os.path.realpath(workspace / "sub"))


def test_model_may_narrow_an_operator_grant(workspace, runs, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", "1")
    result = _run({"goal": "read only", "allow_exec": False, "allow_write": False})
    assert not result.get("isError"), result
    assert runs[0].gate.allow_exec is False


def test_serve_freezes_grants_at_start(workspace, runs, monkeypatch):
    import io
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "local_agent_run",
                          "arguments": {"goal": "x", "allow_exec": True}}}
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", "1")
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()
    grants = local_mcp.AgentRunGrants(workspace=str(workspace), allow_write=False,
                                      allow_exec=False)
    local_mcp.serve(stdin, stdout, grants=grants)
    result = json.loads(stdout.getvalue())["result"]
    assert _error_code(result) == "GRANT_NOT_OPERATOR_APPROVED"
    assert runs == []
