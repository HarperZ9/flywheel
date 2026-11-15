"""Falsifiers for start-configured write/exec grants on the MCP server.

Write and exec belong to whoever starts the server (flags or environment), not
to whoever calls a tool. Load-bearing: (1) a server started without a grant
runs with it off even when an argument asks for it; (2) a server started with a
grant honors it, including for background start/status/result; (3) arguments
narrow a grant and never widen it; (4) ``check`` runs a shell, so it needs the
exec grant; (5) the tool description and README state that an allowed shell is
not path-confined. The launchers are covered in test_mcp_grant_launchers.py and
the other routes to a shell in test_mcp_exec_routes.py.
"""
import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest

import relay.local_mcp as m
from relay.async_runs import DONE, RunRegistry
from relay.mcp_grants import StartGrants, grants_from_env
from relay.remote_mcp import RemoteMcpConfig, process


def _call(name, args):
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    return resp["result"]


def _body(name, args):
    return json.loads(_call(name, args)["content"][0]["text"])


class _Stub:
    name = "stub"

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "done", "model_ref": "stub:grants", "seed": seed}


@pytest.fixture
def seen(monkeypatch):
    """Record the gate each run actually executes with."""
    record = {}

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6, check=None, test_cmd=None,
                       approve=None, compact_budget=0):
        record["allow_write"] = ex.gate.allow_write
        record["allow_exec"] = ex.gate.allow_exec
        record["check"] = check
        ledger.append("assistant", "done", {"backend": "stub", "receipt": {"model_ref": "stub"}})
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "c0", "accepted": True,
                "check_passed": None, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Stub()])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    return record


def _start(monkeypatch, grants):
    # Keep the launch root conftest pinned; these tests are about write and exec.
    monkeypatch.setattr(m, "_GRANTS", replace(grants, root=m._GRANTS.root))


# --- (1) no grant at start: arguments cannot turn write or exec on ---

def test_default_grants_are_both_off():
    assert StartGrants() == StartGrants(allow_write=False, allow_exec=False)
    assert grants_from_env({}) == StartGrants()


def test_arguments_asking_for_write_and_exec_run_with_both_off(monkeypatch, seen):
    _start(monkeypatch, StartGrants())
    body = _body("local_agent_run", {"goal": "g", "allow_write": True, "allow_exec": True})
    assert seen["allow_write"] is False and seen["allow_exec"] is False
    binding = body["request_binding"]
    assert binding["allow_write"] is False and binding["allow_exec"] is False
    assert binding["granted_allow_write"] is False and binding["granted_allow_exec"] is False
    assert binding["requested_allow_write"] is True and binding["requested_allow_exec"] is True


def test_write_argument_alone_cannot_grant_write(monkeypatch, seen):
    _start(monkeypatch, StartGrants())
    _body("local_agent_run", {"goal": "g", "allow_write": True})
    assert seen["allow_write"] is False


def test_check_needs_the_exec_grant(monkeypatch, seen):
    # check runs `subprocess.run(check, shell=True)`. Over MCP the caller is not
    # the operator, so an argument must not be a way to reach a shell.
    _start(monkeypatch, StartGrants(allow_write=True))
    res = _call("local_agent_run", {"goal": "g", "check": "echo hi"})
    assert res.get("isError") is True
    body = json.loads(res["content"][0]["text"])
    assert body["error"]["code"] == "EXEC_NOT_GRANTED"
    assert "check" not in seen   # the agent never ran

    # With the grant, check still needs the run to ask for exec.
    _start(monkeypatch, StartGrants(allow_exec=True))
    res = _call("local_agent_run", {"goal": "g", "check": "echo hi"})
    assert json.loads(res["content"][0]["text"])["error"]["code"] == "EXEC_NOT_GRANTED"
    assert "check" not in seen
    _body("local_agent_run", {"goal": "g", "check": "echo hi", "allow_exec": True})
    assert seen["check"] == "echo hi"


# --- (2) a grant at start is honored, blocking and background ---

def test_an_omitted_argument_asks_for_nothing(monkeypatch, seen):
    # As in 0.2.5, a run that does not ask for write or exec gets neither, even
    # on a server launched with both. A grant is the most a run may ask for.
    _start(monkeypatch, StartGrants(allow_write=True, allow_exec=True))
    body = _body("local_agent_run", {"goal": "g"})
    assert seen == {"allow_write": False, "allow_exec": False, "check": None}
    assert body["request_binding"]["requested_allow_write"] is None
    assert body["request_binding"]["granted_allow_exec"] is True


def test_a_run_gets_what_it_asks_for_up_to_the_grant(monkeypatch, seen):
    _start(monkeypatch, StartGrants(allow_write=True, allow_exec=True))
    _body("local_agent_run", {"goal": "g", "allow_write": True})
    assert seen["allow_write"] is True and seen["allow_exec"] is False
    _body("local_agent_run", {"goal": "g", "allow_write": True, "allow_exec": True})
    assert seen["allow_write"] is True and seen["allow_exec"] is True


def test_exec_grant_implies_write(monkeypatch, seen):
    _start(monkeypatch, StartGrants(allow_exec=True))
    assert m._GRANTS.allow_write is True
    # Asking for exec alone asks for write too, because a shell can write.
    _body("local_agent_run", {"goal": "g", "allow_exec": True})
    assert seen["allow_write"] is True and seen["allow_exec"] is True


def test_background_start_status_result_use_the_start_grants(monkeypatch, tmp_path, seen):
    monkeypatch.setattr(m, "RUNS", RunRegistry(id_source=lambda: "grant-bg",
                                               run_root=str(tmp_path / "runs")))
    _start(monkeypatch, StartGrants(allow_write=True))
    start = _body("local_agent_start", {"goal": "g", "allow_exec": True})
    assert start["request_binding"]["allow_write"] is True
    assert start["request_binding"]["allow_exec"] is False

    result = {"state": "running"}
    for _ in range(400):
        result = _body("local_agent_result", {"run_id": "grant-bg"})
        if result["state"] == DONE:
            break
        time.sleep(0.005)
    assert result["state"] == DONE
    assert seen["allow_write"] is True and seen["allow_exec"] is False
    status = _body("local_agent_status", {"run_id": "grant-bg"})
    assert status["request_binding"]["granted_allow_write"] is True
    reloaded = RunRegistry(run_root=str(tmp_path / "runs")).result("grant-bg")
    assert reloaded["request_binding"]["allow_exec"] is False


# --- (3) arguments narrow, never widen ---

def test_arguments_narrow_the_start_grants(monkeypatch, seen):
    _start(monkeypatch, StartGrants(allow_write=True, allow_exec=True))
    _body("local_agent_run", {"goal": "g", "allow_write": True, "allow_exec": False})
    assert seen["allow_write"] is True and seen["allow_exec"] is False


def test_narrowing_write_also_turns_exec_off(monkeypatch, seen):
    # A shell can write, so a run told "no writes" cannot keep a shell.
    _start(monkeypatch, StartGrants(allow_write=True, allow_exec=True))
    body = _body("local_agent_run", {"goal": "g", "allow_write": False, "allow_exec": True})
    assert seen["allow_write"] is False and seen["allow_exec"] is False
    assert body["request_binding"]["allow_exec"] is False


def test_grant_arguments_are_still_type_checked(monkeypatch, seen):
    _start(monkeypatch, StartGrants(allow_write=True))
    res = _call("local_agent_run", {"goal": "g", "allow_write": "false"})
    assert res.get("isError") is True
    assert json.loads(res["content"][0]["text"])["error"]["code"] == "INVALID_ARGUMENT"


# --- (4) the remote surface keeps its own exec guard under inherited grants ---

def test_remote_posture_refuses_exec_without_touching_the_arguments():
    from relay.mcp_grants import SURFACE_EXEC_REFUSED

    captured = {}

    def h(req):
        captured["args"] = json.loads(json.dumps(req["params"]["arguments"]))
        captured["refused"] = SURFACE_EXEC_REFUSED.get()
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"ok": True}}

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "local_agent_start", "arguments": {"goal": "g"}}})
    headers = {"authorization": "Bearer t", "content-type": "application/json"}
    process(RemoteMcpConfig(token="t", handle=h), "POST", headers, body.encode())
    # The refusal covers an omitted allow_exec, which would otherwise inherit
    # the launch grant, and it leaves the caller's arguments as sent.
    assert captured == {"args": {"goal": "g"}, "refused": True}
    assert SURFACE_EXEC_REFUSED.get() is False   # scoped to that one request

    process(RemoteMcpConfig(token="t", handle=h, allow_remote_exec=True), "POST", headers,
            body.encode())
    assert captured["refused"] is False


# --- (5) the limit is stated where a client and a reader will see it ---

def test_run_and_start_descriptions_state_the_grant_model_and_shell_limit():
    tools = {t["name"]: t for t in m.TOOLS}
    for name in ("local_agent_run", "local_agent_start"):
        desc = tools[name]["description"]
        low = desc.lower()
        assert "not path-confined" in low
        assert "--allow-write" in desc and "--allow-exec" in desc
        assert "RELAY_ALLOW_WRITE" in desc and "RELAY_ALLOW_EXEC" in desc
        assert "only narrow" in low
        props = tools[name]["inputSchema"]["properties"]
        assert "narrow" in props["allow_write"]["description"].lower()
        assert "narrow" in props["allow_exec"]["description"].lower()


def test_readme_states_the_grant_model_and_shell_limit():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "relay --mcp --allow-write" in readme
    assert "RELAY_ALLOW_EXEC" in readme
    assert "not path-confined" in readme


def test_status_and_doctor_report_the_start_grants(monkeypatch):
    _start(monkeypatch, StartGrants(allow_write=True))
    for tool in ("relay.status", "relay.doctor"):
        grants = _body(tool, {})["grants"]
        assert grants == {"allow_write": True, "allow_exec": False,
                          "root": os.path.realpath(m._GRANTS.root),
                          "agent_cli_tiers": False, "shell_path_confined": False}
