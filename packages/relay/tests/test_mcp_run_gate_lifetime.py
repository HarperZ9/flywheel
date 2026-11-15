"""Falsifiers for the gate a run is admitted with, end to end.

Load-bearing: (1) on the remote surface without RELAY_ALLOW_REMOTE_EXEC, a run
that asks for exec on a server launched with it reaches no shell through
``check``, with the real handler and the real agent loop, and the check command
is never started; (2) the remote surface refuses exec on both ``local_agent_run``
and ``local_agent_start``, whether the caller asks for exec or omits it; (3) a
background run keeps the gate and root it was admitted with, even when the
launch grants change before its work runs.
"""
import json
import os

import pytest

import relay.local_loop as loop
import relay.local_mcp as m
from relay.local_session import SessionLedger
from relay.mcp_grants import StartGrants
from relay.remote_mcp import RemoteMcpConfig, process


class _Stub:
    name = "stub"

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "done", "model_ref": "stub:lifetime", "seed": seed}


def _launch(monkeypatch, **grants):
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, **grants))


def _remote(name, args):
    cfg = RemoteMcpConfig(token="t", handle=m.handle)   # remote exec off
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    status, _, raw = process(cfg, "POST", {"authorization": "Bearer t"}, body.encode())
    assert status == 200
    return json.loads(json.loads(raw)["result"]["content"][0]["text"])


class _Deferred:
    """A run registry that stores the work instead of starting a thread, so a
    test can change the launch grants between admission and execution."""

    def __init__(self):
        self.work = []

    def start(self, fn, *, request_binding=None):
        self.work.append(fn)
        return f"deferred-{len(self.work)}"


@pytest.fixture
def gates(monkeypatch):
    """The gate and root each run's executor actually carries."""
    record = []

    def fake_run_agent(agent, goal, ex, ledger, **kwargs):
        record.append({"allow_write": ex.gate.allow_write, "allow_exec": ex.gate.allow_exec,
                       "root": ex.root})
        return {"final": "done", "steps": 1, "verified": True, "final_answer": True,
                "chain_ok": True, "checkpoint": "c0", "accepted": True,
                "check_passed": None, "ledger": ledger}

    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Stub()])
    monkeypatch.setattr(m, "run_agent", fake_run_agent)
    return record


# --- (1) remote check, real handler and real loop ---

def test_remote_check_never_starts_a_shell_without_remote_exec(monkeypatch, tmp_path):
    started = []

    def no_shell(*a, **k):
        started.append(a)
        raise AssertionError("check reached subprocess.run")

    monkeypatch.setattr(loop.subprocess, "run", no_shell)
    monkeypatch.setattr(m, "available_backends", lambda *, model="": [_Stub()])
    _launch(monkeypatch, allow_exec=True)
    for tool in ("local_agent_run", "local_agent_start"):
        body = _remote(tool, {"goal": "g", "root": str(tmp_path), "backend": "stub",
                              "check": "echo pwned > pwned.txt", "allow_exec": True})
        assert body["error"]["code"] == "EXEC_NOT_GRANTED"
        assert body["request_binding"]["remote_exec_refused"] is True
    assert started == []
    assert not (tmp_path / "pwned.txt").exists()


# --- (2) both remote run tools, asked or omitted ---

@pytest.mark.parametrize("tool", ["local_agent_run", "local_agent_start"])
@pytest.mark.parametrize("asked", [{"allow_exec": True}, {}])
def test_remote_runs_get_no_exec_without_remote_exec(monkeypatch, gates, tool, asked):
    deferred = _Deferred()
    monkeypatch.setattr(m, "RUNS", deferred)
    _launch(monkeypatch, allow_exec=True)
    body = _remote(tool, {"goal": "g", "allow_write": True, **asked})
    assert body["request_binding"]["allow_exec"] is False
    for work in deferred.work:
        work(SessionLedger())
    assert gates and all(g["allow_exec"] is False for g in gates)
    assert gates[-1]["allow_write"] is True


# --- (3) a background run keeps its admitted gate ---

def test_a_background_run_keeps_the_gate_it_was_admitted_with(monkeypatch, gates, tmp_path):
    deferred = _Deferred()
    monkeypatch.setattr(m, "RUNS", deferred)
    admitted_root = m._GRANTS.root
    _launch(monkeypatch, allow_exec=True)
    start = json.loads(m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "local_agent_start",
                                            "arguments": {"goal": "g", "allow_exec": True}}})
                       ["result"]["content"][0]["text"])
    assert start["request_binding"]["allow_exec"] is True

    # The launch changes before the stored work runs: no grants, another root.
    m.configure(StartGrants(root=str(tmp_path)))
    assert gates == []
    deferred.work[0](SessionLedger())
    assert gates == [{"allow_write": True, "allow_exec": True,
                      "root": os.path.realpath(admitted_root)}]
    assert m._GRANTS.root == os.path.realpath(tmp_path) != os.path.realpath(admitted_root)
