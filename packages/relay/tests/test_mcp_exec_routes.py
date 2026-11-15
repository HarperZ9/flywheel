"""Falsifiers for the routes to a shell that the launch grants must cover.

Load-bearing: (1) the online codex/claude CLI tiers launch an agentic CLI with
its own shell, so no tool reaches one without the exec grant, and the remote
surface also needs RELAY_ALLOW_REMOTE_EXEC; (2) ``check`` follows the run's
effective exec, so narrowing or the remote guard refuses it even when the launch
granted exec; (3) a write is denied without the grant and performed with it;
(4) the binding names what a caller asked for beyond the grant, and a refusal by
the remote surface is recorded as the surface's, not the caller's.
"""
import json

import pytest

import relay.endpoints as ep
import relay.local_mcp as m
from relay.endpoints import CliBackend
from relay.local_session import SessionLedger
from relay.mcp_grants import StartGrants
from relay.remote_mcp import RemoteMcpConfig, process


def _call(name, args):
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
    return resp["result"]


def _remote(name, args, *, allow_remote_exec=False):
    cfg = RemoteMcpConfig(token="t", handle=m.handle, allow_remote_exec=allow_remote_exec)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    status, _, raw = process(cfg, "POST", {"authorization": "Bearer t"}, body.encode())
    assert status == 200
    return json.loads(raw)["result"]


def _body(res):
    return json.loads(res["content"][0]["text"])


def _code(res):
    assert res.get("isError") is True, res
    return _body(res)["error"]["code"]


def _launch(monkeypatch, **grants):
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, **grants))


class _Stub:
    name = "stub"

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "done", "model_ref": "stub:routes", "seed": seed}


@pytest.fixture
def launched(monkeypatch):
    """An installed codex CLI tier. Every process it would start is recorded, and
    none is started."""
    calls = []

    class _Done:
        returncode, stdout, stderr = 0, "cli answer", ""

    def fake_run(name, args, **kwargs):
        calls.append((name, list(args), kwargs.get("profile")))
        return _Done()

    tier = CliBackend(name="codex-plan", argv=["codex", "-"], profile="codex")
    monkeypatch.setattr(ep, "build_endpoints", lambda **kwargs: [tier])
    monkeypatch.setattr(ep.safe_spawn, "resolve", lambda name, *a, **k: f"/usr/bin/{name}")
    monkeypatch.setattr(ep.safe_spawn, "run", fake_run)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [])
    return calls


@pytest.fixture
def seen(monkeypatch):
    record = {}

    def fake_run_agent(agent, goal, ex, ledger, *, max_steps=6, check=None, test_cmd=None,
                       approve=None, compact_budget=0):
        record.update(allow_write=ex.gate.allow_write, allow_exec=ex.gate.allow_exec,
                      check=check)
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "c0", "accepted": True,
                "check_passed": None, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Stub()])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    return record


# --- (1) the online CLI tiers are exec ---

def test_chat_cannot_launch_a_cli_tier_without_the_exec_grant(monkeypatch, launched):
    _launch(monkeypatch, allow_write=True)
    res = _call("local_agent_chat", {"prompt": "run whoami", "online": True,
                                     "backend": "codex-plan"})
    assert _code(res) == "EXEC_NOT_GRANTED"
    assert launched == []


def test_auto_routing_and_health_leave_the_cli_tier_out_without_exec(monkeypatch, launched):
    _launch(monkeypatch)
    _call("local_agent_chat", {"prompt": "hi", "online": True})
    assert launched == []
    tiers = _body(_call("local_agent_health", {"online": True}))["tiers"]
    assert "codex-plan" not in {t["backend"] for t in tiers}


def test_run_and_start_cannot_launch_a_cli_tier_without_exec(monkeypatch, launched):
    _launch(monkeypatch, allow_write=True)
    for tool in ("local_agent_run", "local_agent_start"):
        res = _call(tool, {"goal": "g", "online": True, "backend": "codex-plan"})
        assert _code(res) == "EXEC_NOT_GRANTED"
    _launch(monkeypatch, allow_exec=True)
    for narrowed in ({"allow_exec": False}, {}):
        res = _call("local_agent_run", {"goal": "g", "online": True, "backend": "codex-plan",
                                        **narrowed})
        assert _code(res) == "EXEC_NOT_GRANTED"
    assert launched == []


def test_the_exec_grant_opens_the_cli_tier(monkeypatch, launched):
    _launch(monkeypatch, allow_exec=True)
    out = _body(_call("local_agent_chat", {"prompt": "hi", "online": True,
                                           "backend": "codex-plan"}))
    assert out["text"] == "cli answer"
    assert launched == [("codex", ["-"], "codex")]


def test_remote_chat_needs_remote_exec_for_a_cli_tier(monkeypatch, launched):
    _launch(monkeypatch, allow_exec=True)
    args = {"prompt": "run whoami", "online": True, "backend": "codex-plan"}
    assert _code(_remote("local_agent_chat", args)) == "EXEC_NOT_GRANTED"
    assert launched == []
    _remote("local_agent_chat", args, allow_remote_exec=True)
    assert len(launched) == 1


# --- (2) check follows the effective exec, not the launch grant ---

def test_narrowed_exec_refuses_check(monkeypatch, seen):
    _launch(monkeypatch, allow_exec=True)
    res = _call("local_agent_run", {"goal": "g", "allow_exec": False, "check": "echo"})
    assert _code(res) == "EXEC_NOT_GRANTED"
    assert seen == {}


def test_remote_check_without_remote_exec_is_refused(monkeypatch, seen):
    # Exec granted at launch, remote exec off: check would open the shell the
    # remote guard exists to keep shut.
    _launch(monkeypatch, allow_exec=True)
    for tool in ("local_agent_run", "local_agent_start"):
        res = _remote(tool, {"goal": "g", "check": "echo hi", "allow_exec": True})
        assert _code(res) == "EXEC_NOT_GRANTED"
    assert seen == {}
    _remote("local_agent_run", {"goal": "g", "check": "echo hi", "allow_exec": True},
            allow_remote_exec=True)
    assert seen["check"] == "echo hi"


# --- (3) a write is denied without the grant and performed with it ---

class _Writer(_Stub):
    def __init__(self):
        self.replies = ['TOOL write_file {"path": "x.txt", "content": "hi"}', "done"]

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.replies.pop(0) if self.replies else "done",
                "model_ref": "stub:w", "seed": seed}


def _write_run(monkeypatch, tmp_path):
    from relay.local_loop import run_agent as real_run_agent

    ledgers = []

    class _Recorded(SessionLedger):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            ledgers.append(self)

    monkeypatch.setattr(m, "run_agent", real_run_agent)
    monkeypatch.setattr(m, "SessionLedger", _Recorded)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Writer()])
    _call("local_agent_run", {"goal": "write x", "root": str(tmp_path), "backend": "stub",
                              "max_steps": 3, "allow_write": True})
    return " ".join(e.content for e in ledgers[0].entries)


def test_write_is_denied_without_the_grant_and_the_ledger_says_so(monkeypatch, tmp_path):
    _launch(monkeypatch)
    text = _write_run(monkeypatch, tmp_path)
    assert not (tmp_path / "x.txt").exists()
    assert "[gate] write disabled" in text


def test_write_is_performed_with_the_grant(monkeypatch, tmp_path):
    _launch(monkeypatch, allow_write=True)
    text = _write_run(monkeypatch, tmp_path)
    assert (tmp_path / "x.txt").read_text() == "hi"
    assert "[gate]" not in text


# --- (4) the binding says who narrowed what ---

def test_grant_shortfall_names_what_was_asked_beyond_the_grant(monkeypatch, seen):
    _launch(monkeypatch)
    body = _body(_call("local_agent_run", {"goal": "g", "allow_write": True,
                                           "allow_exec": True}))
    assert body["request_binding"]["grant_shortfall"] == ["write", "exec"]
    _launch(monkeypatch, allow_exec=True)
    body = _body(_call("local_agent_run", {"goal": "g", "allow_exec": True}))
    assert body["request_binding"]["grant_shortfall"] == []


def test_the_remote_refusal_is_recorded_as_the_surfaces(monkeypatch, seen):
    _launch(monkeypatch, allow_exec=True)
    binding = _body(_remote("local_agent_run", {"goal": "g", "allow_exec": True}))
    binding = binding["request_binding"]
    assert binding["requested_allow_exec"] is True
    assert binding["remote_exec_refused"] is True
    assert binding["allow_exec"] is False and binding["allow_write"] is True
    assert seen["allow_exec"] is False
    local = _body(_call("local_agent_run", {"goal": "g", "allow_exec": True}))
    local = local["request_binding"]
    assert local["remote_exec_refused"] is False and local["allow_exec"] is True
