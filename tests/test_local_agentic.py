"""Falsifiers for the agentic local agent (tools + gate + witnessed ledger + loop).

These back the 'more than a chat client' claim: (1) tools are sandboxed to a root
and default-deny for write/exec, with a denylist even when exec is allowed;
(2) the session ledger is hash-chained and tamper-evident, and round-trips
through save/load; (3) the agentic loop executes gated tools, feeds observations
back, records the whole trajectory, and returns a re-verifiable checkpoint.
"""
import pytest

from harness.local_loop import run_agent
from harness.local_session import SessionLedger
from harness.local_tools import ToolExecutor, ToolGate, parse_tool_calls


# ── tools + gate + sandbox ────────────────────────────────────────────────

def test_parse_tool_calls_skips_malformed():
    text = ('TOOL read_file {"path": "a"}\n'
            'TOOL bad {not json}\n'
            'just prose, no tool\n'
            'TOOL run {"cmd": "ls"}')
    assert parse_tool_calls(text) == [("read_file", {"path": "a"}),
                                      ("run", {"cmd": "ls"})]


def test_read_and_list_are_sandboxed(tmp_path):
    (tmp_path / "in.txt").write_text("data", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path))
    good = ex.execute("read_file", {"path": "in.txt"})
    assert good.ok and good.output == "data"
    escape = ex.execute("read_file", {"path": "../../../../etc/passwd"})
    assert not escape.ok and "escapes root" in escape.output


def test_exec_gate_and_denylist():
    off = ToolExecutor(root=".", gate=ToolGate(allow_exec=False))
    assert not off.execute("run", {"cmd": "echo hi"}).ok        # exec disabled by default
    on = ToolExecutor(root=".", gate=ToolGate(allow_exec=True),
                      runner=lambda cmd, root: (True, "ran"))
    assert on.execute("run", {"cmd": "echo hi"}).ok             # allowed via injected runner
    blocked = on.execute("run", {"cmd": "rm -rf /"})
    assert not blocked.ok and "denylist" in blocked.output      # destructive blocked even when allowed


def test_write_gate_default_deny_then_allowed(tmp_path):
    denied = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = denied.execute("write_file", {"path": "x.txt", "content": "hi"})
    assert not r.ok and not (tmp_path / "x.txt").exists()
    ok = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    w = ok.execute("write_file", {"path": "sub/out.txt", "content": "xyz"})
    assert w.ok and (tmp_path / "sub" / "out.txt").read_text() == "xyz"


def test_unknown_tool_and_tool_exception_are_results_not_crashes(tmp_path):
    ex = ToolExecutor(root=str(tmp_path))
    assert not ex.execute("nope", {}).ok
    assert not ex.execute("read_file", {"path": "missing.txt"}).ok   # exception -> ok=False


def test_edit_file_requires_a_unique_match(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\nb = 1\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    # unique -> applied
    ok = ex.execute("edit_file", {"path": "m.py", "old": "a = 1", "new": "a = 2"})
    assert ok.ok and (tmp_path / "m.py").read_text() == "a = 2\nb = 1\n"
    # not found -> refused, file untouched
    miss = ex.execute("edit_file", {"path": "m.py", "old": "zzz", "new": "q"})
    assert not miss.ok and "not found" in miss.output
    # ambiguous -> refused (both '= 1' lines), file untouched
    (tmp_path / "d.py").write_text("x = 1\ny = 1\n", encoding="utf-8")
    amb = ex.execute("edit_file", {"path": "d.py", "old": " 1", "new": " 9"})
    assert not amb.ok and "matches 2" in amb.output
    assert (tmp_path / "d.py").read_text() == "x = 1\ny = 1\n"


def test_edit_file_is_gated_like_write(tmp_path):
    (tmp_path / "m.py").write_text("k = 1\n", encoding="utf-8")
    denied = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = denied.execute("edit_file", {"path": "m.py", "old": "k = 1", "new": "k = 2"})
    assert not r.ok and "[gate]" in r.output
    assert (tmp_path / "m.py").read_text() == "k = 1\n"          # unchanged


def test_repo_map_tool_lists_symbols(tmp_path):
    (tmp_path / "mod.py").write_text("class Foo:\n    def bar(self):\n        pass\n"
                                     "def top():\n    pass\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path))
    r = ex.execute("repo_map", {"path": "."})
    assert r.ok
    assert "class Foo" in r.output and "def bar" in r.output and "def top" in r.output


# ── witnessed session ledger ──────────────────────────────────────────────

def test_ledger_chains_and_tamper_is_detected():
    led = SessionLedger()
    led.append("user", "hi")
    led.append("assistant", "yo")
    assert led.verify()
    led.entries[0].content = "TAMPERED"
    assert led.verify() is False


def test_ledger_save_load_roundtrip(tmp_path):
    led = SessionLedger()
    led.append("user", "q")
    led.append("assistant", "a", {"backend": "ollama"})
    p = tmp_path / "s.jsonl"
    led.save(str(p))
    back = SessionLedger.load(str(p))
    assert back.verify() and back.checkpoint() == led.checkpoint()
    assert back.transcript() == [{"role": "user", "content": "q"},
                                 {"role": "assistant", "content": "a"}]


# ── the agentic loop ──────────────────────────────────────────────────────

class ScriptedAgent:
    """A fake LocalAgent: returns queued replies, records what it was sent."""

    def __init__(self, replies, backend="stub"):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        text = self._replies.pop(0) if self._replies else "done"
        return {"content": [{"type": "text", "text": text}], "backend": "stub",
                "x_receipt": {"receipt_id": f"rid{len(self.sent)}"}}


def test_edit_receipt_carries_the_post_edit_file_hash(tmp_path):
    """A mutating tool's receipt must bind the edit to a specific file state
    (tenet 3): the post-edit content sha of the target path."""
    import hashlib
    agent = ScriptedAgent(['TOOL write_file {"path": "x.py", "content": "print(1)\\n"}',
                           "done"])
    led = SessionLedger()
    run_agent(agent, "write x.py",
              ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True)),
              led, max_steps=4)
    tr = next(e for e in led.entries if e.kind == "tool_result")
    want = hashlib.sha256((tmp_path / "x.py").read_bytes()).hexdigest()
    assert tr.meta.get("edited", {}).get("x.py") == want


def test_tool_results_carry_an_hmac_sig_when_a_key_is_passed(tmp_path):
    """The per-tool authenticity receipt: with a sign_key, every tool_result
    meta carries a sig a holder of the key can re-verify. Production callers
    must pass a key, or this receipt is dead (tenet 3)."""
    from harness import tool_receipts
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    key = tool_receipts.new_session_key()
    agent = ScriptedAgent(['TOOL read_file {"path": "a.txt"}', "done"])
    led = SessionLedger()
    run_agent(agent, "read a.txt", ToolExecutor(root=str(tmp_path)), led,
              max_steps=4, sign_key=key)
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert tr.meta.get("sig"), "tool_result carries no authenticity sig"


def test_router_agent_signs_tool_results_in_production(tmp_path, monkeypatch):
    """run_router_agent must mint and pass a signing key, and surface a
    key commitment (never the secret key) so the run is authenticity-tagged."""
    import harness.router_agent as ra
    captured = {}

    def spy(agent, goal, executor, ledger, **kw):
        # short-circuit: capture the key, never call the model
        captured["sign_key"] = kw.get("sign_key")
        ledger.append("assistant", "done")
        return {"final": "done", "steps": 1, "checkpoint": "cp",
                "verified": True}

    monkeypatch.setattr(ra, "run_agent", spy)
    out = ra.run_router_agent("noop goal", "serve", root=str(tmp_path),
                              max_steps=1)
    assert captured["sign_key"] is not None, "no signing key was passed"
    assert out["tool_authenticity"]["signed"] is True
    assert len(out["tool_authenticity"]["key_sha256"]) == 64
    # the secret key itself must never appear in the run doc
    import json as _j
    assert captured["sign_key"].hex() not in _j.dumps(out)


def test_loop_executes_tools_and_witnesses_the_full_trajectory(tmp_path):
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    agent = ScriptedAgent(['TOOL read_file {"path": "a.txt"}',
                           "the file says hello world"])
    led = SessionLedger()
    res = run_agent(agent, "what does a.txt say?",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=4)
    assert res["final"] == "the file says hello world"
    assert res["steps"] == 2 and res["verified"] is True
    assert [e.kind for e in led.entries] == \
        ["user", "assistant", "tool_call", "tool_result", "assistant"]
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert "hello world" in tr.content


def test_loop_respects_the_gate_and_keeps_going(tmp_path):
    agent = ScriptedAgent(['TOOL write_file {"path": "x.txt", "content": "hi"}',
                           "I was not allowed to write"])
    led = SessionLedger()
    res = run_agent(agent, "write x.txt",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False)),
                    led, max_steps=3)
    assert not (tmp_path / "x.txt").exists()          # gate held
    assert res["final"] == "I was not allowed to write"
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert "[gate]" in tr.content


def test_loop_stops_at_max_steps_and_still_verifies(tmp_path):
    # a model that always asks for another tool never "finishes"
    agent = ScriptedAgent(['TOOL list_dir {"path": "."}'] * 10)
    led = SessionLedger()
    res = run_agent(agent, "loop forever",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=3)
    assert res["steps"] == 3 and res["verified"] is True
    assert "max_steps" in res["final"]


def test_tools_system_prompt_is_installed_once():
    from harness.local_tools import TOOLS_SYSTEM
    agent = ScriptedAgent(["done", "done again"])
    run_agent(agent, "hi", ToolExecutor(root="."), SessionLedger(), max_steps=1)
    run_agent(agent, "again", ToolExecutor(root="."), SessionLedger(), max_steps=1)  # resume
    assert TOOLS_SYSTEM in agent.system
    assert agent.system.count(TOOLS_SYSTEM) == 1     # guard prevents re-append


def test_test_repair_loop_gates_on_passing_tests():
    # tests fail once, then pass -> the loop keeps going until green
    calls = {"n": 0}

    def runner(cmd, root):
        calls["n"] += 1
        return (calls["n"] >= 2, "FAILED: 1 test" if calls["n"] < 2 else "1 passed")
    agent = ScriptedAgent(["I think it is fixed", "now really fixed"])
    ex = ToolExecutor(root=".", gate=ToolGate(allow_exec=True), runner=runner)
    led = SessionLedger()
    res = run_agent(agent, "fix the bug", ex, led, max_steps=5, test_cmd="pytest -q")
    assert res["tests_pass"] is True and calls["n"] == 2     # ran fail then pass
    gates = [e for e in led.entries if e.meta.get("gate") == "test"]
    assert len(gates) == 2 and gates[0].meta["ok"] is False and gates[1].meta["ok"] is True


def test_test_gate_without_exec_is_reported_not_infinite():
    agent = ScriptedAgent(["done"])
    res = run_agent(agent, "x", ToolExecutor(root=".", gate=ToolGate(allow_exec=False)),
                    SessionLedger(), max_steps=3, test_cmd="pytest")
    assert res["tests_pass"] is False and "exec is disabled" in res["note"]


def test_test_repair_gives_up_at_max_steps_if_never_green():
    agent = ScriptedAgent(["done"] * 10)
    ex = ToolExecutor(root=".", gate=ToolGate(allow_exec=True),
                      runner=lambda c, r: (False, "still failing"))
    res = run_agent(agent, "x", ex, SessionLedger(), max_steps=3, test_cmd="pytest")
    assert res["tests_pass"] is False
