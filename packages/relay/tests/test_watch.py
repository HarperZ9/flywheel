"""Falsifiers for watch mode (parity with aider's editor-agnostic marker comments).

Load-bearing: (1) a marker line is found with surrounding context, an empty
marker (no instruction) is NOT a hit; (2) binary/undecodable/oversized files are
skipped, never guessed at; (3) each marker becomes its OWN witnessed run through
the real gated loop (not a bypass) and the model is told to remove the marker
itself; (4) a marker the model actually removes does not re-fire on the next scan;
(5) one marker's outcome is independent of another's.
"""
from relay.local_loop import run_agent
from relay.local_tools import ToolExecutor, ToolGate
from relay.messages_api import make_receipt
from relay.watch import DEFAULT_MARKER, find_markers, run_watch_once


class ScriptedAgent:
    """A fake LocalAgent: returns queued replies, records what it was sent."""

    def __init__(self, replies):
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


def test_finds_a_marker_with_instruction_and_context(tmp_path):
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n    return a - b  # RELAY: fix this, should add not subtract\n",
        encoding="utf-8")
    hits = find_markers(str(tmp_path))
    assert len(hits) == 1
    h = hits[0]
    assert h["path"] == "app.py" and h["line"] == 2
    assert h["instruction"] == "fix this, should add not subtract"
    assert "def add" in h["context"]


def test_marker_with_no_instruction_is_not_a_hit(tmp_path):
    (tmp_path / "x.py").write_text("y = 1  # RELAY:\n", encoding="utf-8")
    assert find_markers(str(tmp_path)) == []


def test_binary_and_oversized_files_are_skipped_not_guessed_at(tmp_path):
    (tmp_path / "img.bin").write_bytes(bytes(range(256)) * 4)
    huge = tmp_path / "huge.py"
    huge.write_text("# RELAY: too big\n" + "x" * 10, encoding="utf-8")
    hits = find_markers(str(tmp_path), marker=DEFAULT_MARKER)
    from relay import watch as w
    old = w._MAX_FILE_BYTES
    w._MAX_FILE_BYTES = 5     # force "huge.py" over the cap deterministically
    try:
        hits2 = find_markers(str(tmp_path))
    finally:
        w._MAX_FILE_BYTES = old
    assert hits == [h for h in hits if h["path"] != "img.bin"]   # binary never crashed the scan
    assert hits2 == []                                            # over-cap file skipped


def test_custom_marker_string_is_honored(tmp_path):
    (tmp_path / "a.py").write_text("z = 1  # TODO-AI: rename z\n", encoding="utf-8")
    assert find_markers(str(tmp_path), marker=DEFAULT_MARKER) == []
    hits = find_markers(str(tmp_path), marker="TODO-AI:")
    assert hits and hits[0]["instruction"] == "rename z"


def test_run_watch_once_runs_each_marker_through_the_real_gated_loop(tmp_path):
    (tmp_path / "a.py").write_text("x = 1  # RELAY: double it\n", encoding="utf-8")
    agent = ScriptedAgent(["done, doubled it"])
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    results = run_watch_once(agent, ex)
    assert len(results) == 1
    r = results[0]
    assert r["path"] == "a.py" and r["line"] == 1 and r["verified"] is True
    # the goal handed to the agent names the file, the instruction, and tells it
    # to remove the marker itself via the SAME tool the model always uses
    assert "double it" in agent.sent[0] and "edit_file" in agent.sent[0]


def test_a_marker_the_model_removes_does_not_refire(tmp_path):
    (tmp_path / "a.py").write_text("x = 1  # RELAY: double it\n", encoding="utf-8")
    agent = ScriptedAgent([
        'TOOL edit_file {"path": "a.py", "old": "x = 1  # RELAY: double it\\n", "new": "x = 2\\n"}',
        "done"])
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    first = run_watch_once(agent, ex)
    assert len(first) == 1 and first[0]["verified"] is True
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\n"
    # scan again: the marker is gone, so nothing re-fires (no new agent call needed)
    assert find_markers(str(tmp_path)) == []


def test_two_markers_are_independent_witnessed_runs(tmp_path):
    (tmp_path / "a.py").write_text("a = 1  # RELAY: fix a\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1  # RELAY: fix b\n", encoding="utf-8")
    agent = ScriptedAgent(["done a", "done b"])
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    results = run_watch_once(agent, ex)
    assert {r["path"] for r in results} == {"a.py", "b.py"}
    assert all(r["verified"] for r in results)


def test_run_watch_once_uses_the_real_witnessed_loop(tmp_path, monkeypatch):
    # not a reimplementation: run_watch_once must call the SAME run_agent the
    # rest of relay uses, so a marker fix is exactly as accountable as any run.
    import relay.watch as w
    calls = []
    real = run_agent

    def spy(*a, **k):
        calls.append(a[1])   # the goal string
        return real(*a, **k)
    monkeypatch.setattr(w, "run_agent", spy)
    (tmp_path / "a.py").write_text("x = 1  # RELAY: fix x\n", encoding="utf-8")
    agent = ScriptedAgent(["done"])
    run_watch_once(agent, ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True)))
    assert len(calls) == 1 and "fix x" in calls[0]
