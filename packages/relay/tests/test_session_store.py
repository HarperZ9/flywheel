"""Sessions that follow you: a saved relay session lists and reopens across devices,
a tampered saved session reads as unverified rather than hidden, and run_agent
resumes from a loaded ledger by seeding the model's context and continuing the chain."""
import json

from relay.local_loop import run_agent
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate
from relay.messages_api import make_receipt
from relay.session_store import get_session, list_sessions


def _save(tmp_path, sid, goal="do the thing"):
    led = SessionLedger()
    led.append("user", goal)
    led.append("assistant", "on it")
    led.save(str(tmp_path / f"{sid}.jsonl"))
    return led


def test_list_sessions_summarizes_each_saved_ledger(tmp_path):
    _save(tmp_path, "sess-a", goal="fix the parser")
    _save(tmp_path, "sess-b", goal="add a test")
    out = list_sessions(str(tmp_path))
    assert out["count"] == 2
    assert {s["id"] for s in out["sessions"]} == {"sess-a", "sess-b"}
    a = next(s for s in out["sessions"] if s["id"] == "sess-a")
    assert a["goal"] == "fix the parser" and a["verified"] is True and a["entries"] == 2


def test_get_session_returns_the_transcript(tmp_path):
    _save(tmp_path, "sess-x", goal="explain the loop")
    got = get_session(str(tmp_path), "sess-x")
    assert got["id"] == "sess-x" and got["verified"] is True
    assert [m["role"] for m in got["transcript"]] == ["user", "assistant"]
    assert got["transcript"][0]["content"] == "explain the loop"


def test_a_missing_session_is_a_typed_error(tmp_path):
    assert "error" in get_session(str(tmp_path), "nope")


def test_empty_dir_lists_nothing(tmp_path):
    assert list_sessions(str(tmp_path / "none"))["count"] == 0


def test_a_tampered_saved_session_reads_unverified(tmp_path):
    _save(tmp_path, "sess-t")
    path = tmp_path / "sess-t.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])           # corrupt a recorded content, leave its hash
    rec["content"] = "TAMPERED"
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines), encoding="utf-8")
    out = list_sessions(str(tmp_path))
    assert out["sessions"][0]["verified"] is False   # honest: marked, not hidden


class _HistAgent:
    def __init__(self, replies):
        self.system = "base"
        self._r = list(replies)
        self.history = []

    def send(self, message):
        self.history.append({"role": "user", "content": message})
        text = self._r.pop(0) if self._r else "done"
        self.history.append({"role": "assistant", "content": text})
        rec = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub", "x_receipt": rec}


def test_run_agent_resumes_from_a_saved_ledger(tmp_path):
    _save(tmp_path, "resume-me", goal="we were refactoring the parser")
    loaded = SessionLedger.load(str(tmp_path / "resume-me.jsonl"))
    before = len(loaded.entries)
    agent = _HistAgent(["done"])
    result = run_agent(agent, "continue where we left off",
                       ToolExecutor(root=str(tmp_path), gate=ToolGate()), loaded, max_steps=2)
    # the model saw the prior conversation (history seeded from the transcript)
    assert any("refactoring the parser" in m["content"] for m in agent.history)
    # the resumed ledger continued and still verifies as one hash chain
    assert len(loaded.entries) > before and result["chain_ok"]
