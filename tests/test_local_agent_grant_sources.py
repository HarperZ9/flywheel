"""Where local_agent_run authority comes from, and what it may never cover.

The operator grants write, exec, online model tiers and the workspace when the
server starts. These tests pin the sources and their precedence (an explicit
start flag wins over the inherited environment), the online and plan-mode
backend grant, and the protected locations a run may never use as its root:
the user home directory itself and anything that contains or sits inside the
Flywheel home, where lanes.json and the signing keys live.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

import harness.local_mcp as local_mcp
from harness import local_agent_cli
from harness import local_agent_grants as grants_mod
from harness.local_agent_grants import GrantRefusal, grants_from_config

GRANT_ENV = ("FLYWHEEL_LOCAL_AGENT_ALLOW_WRITE", "FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC",
             "FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE", "FLYWHEEL_LOCAL_AGENT_WORKSPACE")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    (root / "sub").mkdir(parents=True)
    for name in GRANT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "flywheel-home"))
    monkeypatch.chdir(tmp_path)
    return root


@pytest.fixture
def runs(monkeypatch):
    seen = []

    def fake_run_agent(agent, goal, executor, ledger, **kwargs):
        seen.append((agent, executor))
        return {"final": "done", "steps": 0, "verified": True, "checkpoint": "0" * 64}

    monkeypatch.setattr(local_mcp, "run_agent", fake_run_agent)
    return seen


def _request(name, arguments):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def _cli(monkeypatch, capsys, argv, arguments):
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        json.dumps(_request("local_agent_run", arguments)) + "\n"))
    assert local_agent_cli.main(argv) == 0
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])["result"]


def _code(result):
    assert result.get("isError") is True, result
    return json.loads(result["content"][0]["text"])["error"]["code"]


def _run(arguments, name="local_agent_run"):
    return local_mcp.handle(_request(name, arguments))["result"]


def test_cli_allow_exec_flag_grants_exec_and_not_write(workspace, runs, monkeypatch, capsys):
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    result = _cli(monkeypatch, capsys, ["--mcp", "--root", str(workspace), "--allow-exec"],
                  {"goal": "x", "allow_exec": True})
    assert not result.get("isError"), result
    (_, executor), = runs
    assert executor.gate.allow_exec is True
    assert executor.gate.allow_write is False


@pytest.mark.parametrize("value", ("0", "false", "no", ""))
def test_env_exec_value_that_is_not_true_grants_nothing(workspace, runs, monkeypatch, value):
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", value)
    grants = grants_from_config(workspace=str(workspace))
    assert grants.allow_exec is False


def test_explicit_root_flag_wins_over_the_environment_workspace(workspace, runs,
                                                               monkeypatch, capsys):
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(workspace))
    narrow = workspace / "sub"
    result = _cli(monkeypatch, capsys, ["--mcp", "--root", str(narrow)], {"goal": "x"})
    assert not result.get("isError"), result
    (_, executor), = runs
    assert os.path.normcase(os.path.realpath(executor.root)) == os.path.normcase(
        os.path.realpath(narrow))


def test_no_allow_exec_flag_overrides_an_inherited_env_grant(workspace, runs,
                                                             monkeypatch, capsys):
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_EXEC", "1")
    result = _cli(monkeypatch, capsys, ["--mcp", "--root", str(workspace), "--no-allow-exec"],
                  {"goal": "x", "allow_exec": True})
    assert _code(result) == "GRANT_NOT_OPERATOR_APPROVED"
    assert runs == []


@pytest.mark.parametrize("arguments, code", (
    ({"goal": "x", "online": True}, "GRANT_NOT_OPERATOR_APPROVED"),
    ({"goal": "x", "online": "false"}, "INVALID_GRANT_ARGUMENT"),
    ({"goal": "x", "backend": "claude-plan"}, "GRANT_NOT_OPERATOR_APPROVED"),
    ({"goal": "x", "online": False, "backend": "codex-plan"}, "GRANT_NOT_OPERATOR_APPROVED"),
    ({"goal": "x", "backend": 7}, "INVALID_GRANT_ARGUMENT"),
))
def test_model_cannot_select_online_or_plan_tiers(workspace, runs, monkeypatch,
                                                  arguments, code):
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(workspace))
    monkeypatch.setattr(local_mcp, "_agent", lambda args: pytest.fail("agent built"))
    assert _code(_run(arguments)) == code
    assert runs == []


def test_chat_cannot_enable_online_tiers_without_the_grant(workspace, monkeypatch):
    monkeypatch.setattr(local_mcp, "_agent", lambda args: pytest.fail("agent built"))
    result = _run({"prompt": "hi", "online": True, "backend": "claude-plan"},
                  name="local_agent_chat")
    assert _code(result) == "GRANT_NOT_OPERATOR_APPROVED"


def test_granted_plan_backend_runs_in_the_resolved_root(workspace, runs, monkeypatch):
    import harness.endpoints as endpoints
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(workspace))
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE", "1")
    cli = endpoints.CliBackend("claude-plan", ["claude", "{prompt}"],
                               runner=lambda cmd: (0, b"ok", b""))
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **kw: [cli])
    result = _run({"goal": "x", "online": True, "backend": "claude-plan", "root": "sub"})
    assert not result.get("isError"), result
    (agent, executor), = runs
    assert cli in agent.backends
    assert os.path.normcase(cli.cwd) == os.path.normcase(os.path.realpath(workspace / "sub"))


def test_cli_backend_passes_its_cwd_to_the_process(monkeypatch, tmp_path):
    import harness.endpoints as endpoints
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, stdout=b"ok", stderr=b"")

    monkeypatch.setattr(endpoints.subprocess, "run", fake_run)
    backend = endpoints.CliBackend("claude-plan", ["claude", "{prompt}"], cwd=str(tmp_path))
    backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                 temperature=0.0, seed=0)
    assert seen["cwd"] == str(tmp_path)


def test_workspace_containing_the_flywheel_home_is_refused(workspace, runs, monkeypatch):
    home = workspace / ".flywheel"
    home.mkdir()
    (home / "lanes.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    # An explicitly chosen workspace that holds the Flywheel home is refused.
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(workspace))
    assert _code(_run({"goal": "x"})) == "WORKSPACE_PROTECTED"
    # A default (working directory) workspace is checked per run.
    monkeypatch.delenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE")
    monkeypatch.chdir(workspace)
    assert _code(_run({"goal": "x"})) == "ROOT_PROTECTED"
    assert _code(_run({"goal": "x", "root": ".flywheel"})) == "ROOT_PROTECTED"
    assert runs == []
    assert not _run({"goal": "x", "root": "sub"}).get("isError")


def test_user_home_itself_is_refused_as_a_root(workspace, runs, monkeypatch):
    monkeypatch.setenv("HOME", str(workspace))
    monkeypatch.setenv("USERPROFILE", str(workspace))
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(local_mcp, "_agent", lambda args: object())
    assert _code(_run({"goal": "x"})) == "ROOT_PROTECTED"
    assert runs == []
    assert not _run({"goal": "x", "root": "sub"}).get("isError")


def test_explicit_protected_workspace_is_refused_at_start(workspace, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(workspace / ".flywheel"))
    with pytest.raises(GrantRefusal) as refused:
        grants_from_config(workspace=str(workspace))
    assert refused.value.code == "WORKSPACE_PROTECTED"
    assert local_agent_cli.main(["--mcp", "--root", str(workspace)]) == 2


def test_gateway_pins_its_root_as_the_local_agent_workspace(tmp_path):
    env = {}
    grants_mod.pin_gateway_workspace(tmp_path, env)
    assert env["FLYWHEEL_LOCAL_AGENT_WORKSPACE"] == str(tmp_path.resolve())
    kept = {"FLYWHEEL_LOCAL_AGENT_WORKSPACE": "operator-choice"}
    grants_mod.pin_gateway_workspace(tmp_path, kept)
    assert kept["FLYWHEEL_LOCAL_AGENT_WORKSPACE"] == "operator-choice"


def test_server_started_with_a_protected_workspace_keeps_serving(workspace, runs,
                                                                monkeypatch, capsys):
    # The gateway pins its own --root as the workspace. If that root is protected,
    # the lane must still answer health and chat; only runs are refused.
    monkeypatch.setenv("FLYWHEEL_HOME", str(workspace / ".flywheel"))
    monkeypatch.setenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", str(workspace))
    monkeypatch.setattr(local_mcp, "_agent", lambda args: pytest.fail("agent built"))
    requests = [dict(_request("local_agent_run", {"goal": "x"}), id=1),
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    stdout = io.StringIO()
    assert local_mcp.serve([json.dumps(r) + "\n" for r in requests], stdout) == 0
    first, second = (json.loads(line) for line in stdout.getvalue().splitlines())
    assert _code(first["result"]) == "WORKSPACE_PROTECTED"
    assert any(tool["name"] == "local_agent_run" for tool in second["result"]["tools"])
    assert "WORKSPACE_PROTECTED" in capsys.readouterr().err
    assert runs == []
