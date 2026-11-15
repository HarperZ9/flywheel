"""Falsifiers for the agentic local agent (tools + gate + witnessed ledger + loop).

These back the 'more than a chat client' claim: (1) tools are sandboxed to a root
and default-deny for write/exec, with a denylist even when exec is allowed;
(2) the session ledger is hash-chained and tamper-evident, and round-trips
through save/load; (3) the agentic loop executes gated tools, feeds observations
back, records the whole trajectory, and returns a re-verifiable checkpoint.
"""
import json

import pytest

from relay.local_agent import BackendError
from relay.local_loop import run_agent, verify_receipts, witnessed_edit_paths
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate, parse_tool_calls
from relay.messages_api import make_receipt, recompute_receipt_id


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


def test_exec_implies_write_capability(tmp_path):
    # A shell can write, so --allow-exec cannot honestly keep files immutable. The
    # gate no longer presents writes as 'off' while exec is on: enabling exec
    # enables write, consistently — write_file is allowed, not falsely gated-off,
    # exactly the capability the run tool already grants.
    assert ToolGate(allow_exec=True).allow_write is True
    assert ToolGate(allow_exec=False).allow_write is False       # exec off -> unchanged
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True))
    w = ex.execute("write_file", {"path": "a.txt", "content": "x"})
    assert w.ok and (tmp_path / "a.txt").read_text() == "x"


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
    """A fake LocalAgent: returns queued replies, records what it was sent. Emits a
    real per-turn receipt (full fields) so the loop's receipt re-derivation is
    exercised, not stubbed away."""

    def __init__(self, replies, backend="stub"):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        text = self._replies.pop(0) if self._replies else "done"
        receipt = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub",
                "x_receipt": receipt}


class FailingAgent:
    """Succeeds for the scripted replies, then every backend fails (BackendError),
    to exercise a mid-loop endpoint death."""

    def __init__(self, replies):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if not self._replies:
            raise BackendError("all healthy backends failed: serve; ollama")
        text = self._replies.pop(0)
        receipt = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub",
                "x_receipt": receipt}


def test_loop_executes_tools_and_witnesses_the_full_trajectory(tmp_path):
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    agent = ScriptedAgent(['TOOL read_file {"path": "a.txt"}',
                           "the file says hello world"])
    led = SessionLedger()
    res = run_agent(agent, "what does a.txt say?",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=4)
    assert res["final"] == "the file says hello world"
    assert res["steps"] == 2 and res["verified"] is True
    # the continuation prompt the model actually saw is recorded as a user turn too
    assert [e.kind for e in led.entries] == \
        ["user", "assistant", "tool_call", "tool_result", "user", "assistant"]
    cont = led.entries[4]
    assert cont.kind == "user" and "TOOL RESULTS" in cont.content
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert "hello world" in tr.content


def test_loop_requests_durable_checkpoints_after_meaningful_progress(tmp_path):
    class DurableProgressLedger(SessionLedger):
        def __init__(self):
            super().__init__()
            self.persisted_kinds = []

        def persist_checkpoint(self):
            self.persisted_kinds.append([e.kind for e in self.entries])
            return {"persisted": True, "entries": len(self.entries)}

    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    agent = ScriptedAgent(['TOOL read_file {"path": "a.txt"}',
                           "the file says hello world"])
    led = DurableProgressLedger()

    run_agent(agent, "what does a.txt say?",
              ToolExecutor(root=str(tmp_path)), led, max_steps=4)

    assert ["user", "assistant"] in led.persisted_kinds
    assert ["user", "assistant", "tool_call", "tool_result", "user"] in led.persisted_kinds


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


def test_loop_stops_at_max_steps_and_reports_an_honest_verdict(tmp_path):
    # a model that always asks for another tool never "finishes". max_steps
    # exhaustion is NOT a verified run: the chain is intact (chain_ok) but no real
    # final answer was produced, so the composite verdict is honestly False.
    agent = ScriptedAgent(['TOOL list_dir {"path": "."}'] * 10)
    led = SessionLedger()
    res = run_agent(agent, "loop forever",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=3)
    assert res["steps"] == 3 and "max_steps" in res["final"]
    assert res["chain_ok"] is True          # in-memory integrity holds
    assert res["final_answer"] is False     # but no answer was produced
    assert res["verified"] is False         # so the composite is not a vacuous True


def test_acceptance_check_passes_is_witnessed_and_accepted(tmp_path):
    # the agent finishes; an operator-supplied check runs, passes, and is recorded on
    # the ledger. A run is ACCEPTED only when the trajectory verifies AND the check holds.
    agent = ScriptedAgent(['TOOL write_file {"path": "x.txt", "content": "hi"}', "done"])
    led = SessionLedger()
    res = run_agent(agent, "write x.txt",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                                 runner=lambda cmd, root: (True, "3 passed")),
                    led, max_steps=3, check="pytest -q")
    assert res["check_passed"] is True
    assert res["verified"] is True and res["accepted"] is True
    chk = next(e for e in led.entries if e.kind == "check")   # the check is on the record
    assert chk.meta["cmd"] == "pytest -q" and chk.meta["ok"] is True
    assert "3 passed" in chk.content


def test_failing_acceptance_check_blocks_acceptance_even_when_verified(tmp_path):
    agent = ScriptedAgent(['TOOL write_file {"path": "x.txt", "content": "bug"}', "done"])
    led = SessionLedger()
    res = run_agent(agent, "write x.txt",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                                 runner=lambda cmd, root: (False, "1 failed")),
                    led, max_steps=3, check="pytest -q")
    assert res["verified"] is True          # the trajectory itself is a provable run
    assert res["check_passed"] is False
    assert res["accepted"] is False         # but a failed check is not accepted
    chk = next(e for e in led.entries if e.kind == "check")
    assert chk.meta["ok"] is False


def test_no_check_means_accepted_equals_verified(tmp_path):
    agent = ScriptedAgent(["done"])
    led = SessionLedger()
    res = run_agent(agent, "just answer", ToolExecutor(root=str(tmp_path)), led, max_steps=2)
    assert res["check_passed"] is None
    assert res["accepted"] == res["verified"]
    assert not any(e.kind == "check" for e in led.entries)


def test_acceptance_check_runs_in_the_executor_root(tmp_path):
    seen = {}
    def runner(cmd, root):
        seen["cmd"], seen["root"] = cmd, root
        return True, "ok"
    agent = ScriptedAgent(["done"])
    run_agent(agent, "answer",
              ToolExecutor(root=str(tmp_path), runner=runner),
              SessionLedger(), max_steps=2, check="make test")
    assert seen["cmd"] == "make test" and seen["root"] == str(tmp_path)


def test_a_passing_check_is_not_accepted_when_the_agent_edited_the_test(tmp_path):
    # the reward-hacking guard: the agent makes the check green by rewriting the test
    # that grades it. The check "passes", but the pass is not trusted, so the run is
    # NOT accepted -- a gamed green never gets committed.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text("def test_x():\n    assert False\n",
                                                     encoding="utf-8")
    agent = ScriptedAgent([
        'TOOL write_file {"path": "tests/test_core.py", "content": "def test_x():\\n    pass\\n"}',
        "done, tests pass now"])
    led = SessionLedger()
    res = run_agent(agent, "make the tests pass",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                                 runner=lambda cmd, root: (True, "1 passed")),
                    led, max_steps=3, check="pytest -q")
    assert res["check_passed"] is True          # the check reported green...
    assert res["integrity"]["clean"] is False   # ...but the agent edited the grader
    assert res["check_trusted"] is False
    assert res["accepted"] is False             # so the gamed pass is refused
    assert any(f["kind"] == "edited_protected_file" for f in res["integrity"]["flags"])


def test_a_clean_passing_check_is_accepted(tmp_path):
    # editing real source (not the test) and passing the check is an honest, accepted run
    agent = ScriptedAgent([
        'TOOL write_file {"path": "app.py", "content": "def add(a, b):\\n    return a + b\\n"}',
        "done"])
    led = SessionLedger()
    res = run_agent(agent, "implement add",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                                 runner=lambda cmd, root: (True, "2 passed")),
                    led, max_steps=3, check="pytest -q")
    assert res["check_passed"] is True and res["integrity"]["clean"] is True
    assert res["check_trusted"] is True and res["accepted"] is True


def test_acceptance_check_that_cannot_run_is_a_witnessed_failure_not_a_raise(tmp_path):
    # a check that errors (bad cwd, a raising runner) must fail CLOSED and be witnessed,
    # never propagate and discard the checkpoint the loop built.
    def boom(cmd, root):
        raise NotADirectoryError("no such working directory")
    agent = ScriptedAgent(["done"])
    led = SessionLedger()
    res = run_agent(agent, "answer", ToolExecutor(root=str(tmp_path), runner=boom),
                    led, max_steps=2, check="pytest -q")
    assert res["check_passed"] is False and res["accepted"] is False
    chk = next(e for e in led.entries if e.kind == "check")
    assert chk.meta["ok"] is False and "errored" in chk.content
    assert res["checkpoint"] == led.checkpoint()      # the run is still witnessed


def test_cli_does_not_pass_or_commit_a_run_that_never_finished(tmp_path, monkeypatch):
    # the fail-open the review caught: a --check run that hits max_steps / backend death
    # has check_passed None (the check never ran). It must NOT auto-commit and must exit
    # non-zero — gating is on `accepted`, not merely on "the check didn't fail".
    from relay import local_agent_cli as cli

    class _Live:
        def live_backend(self):
            return object()
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live())
    monkeypatch.setattr(cli, "run_agent",
                        lambda *a, **k: {"final": "[max_steps]", "steps": 3, "entries": 5,
                                         "checkpoint": "c" * 32, "verified": False,
                                         "accepted": False, "check_passed": None,
                                         "review": {"reviewability": 0.0, "edited_unread": [], "unverified_edits": [], "failed_calls": 0},
                                         "risk": {"demands": []}})
    called = {"commit": False}
    monkeypatch.setattr(cli, "commit_run",
                        lambda *a, **k: (called.update(commit=True), {"committed": True, "sha": "x"})[1])
    rc = cli.main([str(tmp_path / "p"), "--agent", "--auto-commit",
                   "--check", "pytest -q", "--root", str(tmp_path)])
    assert rc == 1                       # an unfinished run is not success
    assert called["commit"] is False     # its partial, unchecked edits are not committed


def test_cli_skips_commit_and_exits_nonzero_when_the_check_fails(tmp_path, monkeypatch):
    # the CLI must never auto-commit a run whose acceptance check failed, and must
    # exit non-zero so it works as a CI gate over the agent's own edits.
    from relay import local_agent_cli as cli

    class _Live:
        def live_backend(self):
            return object()
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live())
    monkeypatch.setattr(cli, "run_agent",
                        lambda *a, **k: {"final": "done", "steps": 1, "entries": 3,
                                         "checkpoint": "c" * 32, "verified": True,
                                         "accepted": False, "check_passed": False,
                                         "integrity": {"clean": True, "flag_count": 0},
                                         "review": {"reviewability": 0.0, "edited_unread": [], "unverified_edits": [], "failed_calls": 0},
                                         "risk": {"demands": []}})
    called = {"commit": False}
    def _no_commit(*a, **k):
        called["commit"] = True
        return {"committed": True, "sha": "deadbeef"}
    monkeypatch.setattr(cli, "commit_run", _no_commit)

    rc = cli.main([str(tmp_path / "x"), "--agent", "--auto-commit",
                   "--check", "pytest -q", "--root", str(tmp_path)])
    assert rc == 1                       # failed check -> non-zero exit (CI gate)
    assert called["commit"] is False     # and the broken tree was never committed


def test_tools_system_prompt_is_installed_once():
    from relay.local_tools import TOOLS_SYSTEM
    agent = ScriptedAgent(["done", "done again"])
    run_agent(agent, "hi", ToolExecutor(root="."), SessionLedger(), max_steps=1)
    run_agent(agent, "again", ToolExecutor(root="."), SessionLedger(), max_steps=1)  # resume
    assert TOOLS_SYSTEM in agent.system
    assert agent.system.count(TOOLS_SYSTEM) == 1     # guard prevents re-append


# ── witnessed loop: failures, full receipts, honest verdict ────────────────

def test_mid_loop_backend_failure_is_recorded_not_an_uncaught_raise(tmp_path):
    # 1 good step (a tool call), then every backend dies. The partial work must be
    # witnessed with an error entry + checkpoint, not thrown away as a traceback.
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    agent = FailingAgent(['TOOL read_file {"path": "a.txt"}'])   # then send() raises
    led = SessionLedger()
    res = run_agent(agent, "read it", ToolExecutor(root=str(tmp_path)), led, max_steps=4)
    kinds = [e.kind for e in led.entries]
    assert "error" in kinds                                   # the failure is on the record
    err = next(e for e in led.entries if e.kind == "error")
    assert "backends failed" in err.content
    assert res["final_answer"] is False and res["verified"] is False
    assert res["chain_ok"] is True and res["checkpoint"] == led.checkpoint()


def test_assistant_entries_store_a_re_derivable_receipt(tmp_path):
    agent = ScriptedAgent(["the answer"])
    led = SessionLedger()
    run_agent(agent, "q", ToolExecutor(root=str(tmp_path)), led, max_steps=2)
    a = next(e for e in led.entries if e.kind == "assistant")
    rec = a.meta["receipt"]
    # the FULL receipt is stored (not just an opaque id), so a stranger can re-derive it
    assert {"request_hash", "prompt_hash", "response_hash", "model_ref"} <= set(rec)
    assert recompute_receipt_id(rec) == rec["receipt_id"]


def test_verify_receipts_is_fail_closed_on_a_tampered_receipt(tmp_path):
    agent = ScriptedAgent(["the answer"])
    led = SessionLedger()
    res = run_agent(agent, "q", ToolExecutor(root=str(tmp_path)), led, max_steps=2)
    assert res["receipts_ok"] is True
    # tamper the stored response_hash: the receipt_id no longer re-derives
    a = next(e for e in led.entries if e.kind == "assistant")
    a.meta["receipt"]["response_hash"] = "0" * 16
    assert verify_receipts(led) is False


def test_load_rejects_a_tampered_ledger(tmp_path):
    led = SessionLedger()
    led.append("user", "hi")
    led.append("assistant", "yo")
    p = tmp_path / "s.jsonl"
    led.save(str(p))
    lines = p.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["content"] = "HACKED"                                 # break the chain
    lines[0] = json.dumps(obj)
    p.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="verify"):
        SessionLedger.load(str(p))


def test_witnessed_edit_paths_are_only_the_recorded_write_targets():
    led = SessionLedger()
    led.append("user", "goal")
    led.append("tool_call", 'write_file {"content": "x", "path": "src/a.py"}')
    led.append("tool_call", 'edit_file {"new": "n", "old": "o", "path": "src/b.py"}')
    led.append("tool_call", 'run {"cmd": "echo pwned > src/c.py"}')   # shell write: NOT witnessed
    led.append("tool_call", 'read_file {"path": "src/d.py"}')          # a read is not an edit
    assert witnessed_edit_paths(led) == ["src/a.py", "src/b.py"]


# ── test-repair loop: the same rich verdict as `check`, but retrying ───────

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
    assert res["check_passed"] is True and res["accepted"] is True and calls["n"] == 2
    gates = [e for e in led.entries if e.meta.get("gate") == "test"]
    assert len(gates) == 2 and gates[0].meta["ok"] is False and gates[1].meta["ok"] is True


def test_test_gate_without_exec_is_reported_not_infinite():
    agent = ScriptedAgent(["done"])
    res = run_agent(agent, "x", ToolExecutor(root=".", gate=ToolGate(allow_exec=False)),
                    SessionLedger(), max_steps=3, test_cmd="pytest")
    assert res["check_passed"] is False and res["accepted"] is False
    assert "exec is disabled" in res["note"]


def test_test_repair_gives_up_at_max_steps_if_never_green():
    agent = ScriptedAgent(["done"] * 10)
    ex = ToolExecutor(root=".", gate=ToolGate(allow_exec=True),
                      runner=lambda c, r: (False, "still failing"))
    res = run_agent(agent, "x", ex, SessionLedger(), max_steps=3, test_cmd="pytest")
    assert res["check_passed"] is False and res["accepted"] is False
    assert res["final_answer"] is False   # never produced an accepted final answer
