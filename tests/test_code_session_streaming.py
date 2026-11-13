"""Streamed model text and command output in a coding session.

A scripted backend stands in for the model, so no model and no network is
used. The command-output tests start a real command in this host's sandbox
and skip where the host has none.
"""
import io
import os
import time

import pytest

from harness.code_session import cli
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import (Indented, LineGate, OutputTail, live,
                                            streamed_send)
from harness.local_agent import BackendError

REPLIES = ['I will write the note.\nTOOL write_file {"path": "n.txt", "content": "hi"}',
           "Wrote n.txt.\nNothing else changed."]


class Script:
    """Replies in order through `chat`; cannot stream."""
    name, model = "script", "script-1"

    def __init__(self, replies):
        self.replies = list(replies)

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": self.replies.pop(0), "model_ref": "script:script-1", "seed": seed}


class StreamScript(Script):
    """The same replies, also available seven characters at a time."""

    def __init__(self, replies, fail_after=None):
        super().__init__(replies)
        self.fail_after = fail_after

    def chat_stream(self, messages, *, system, max_tokens, temperature, seed):
        text = self.replies[0]
        for count, start in enumerate(range(0, len(text), 7)):
            if self.fail_after is not None and count >= self.fail_after:
                raise BackendError("stream dropped")
            yield text[start:start + 7]
        self.replies.pop(0)
        return "script:script-1"


def _session(tmp_path, backend):
    return new_session(build_agent([backend]), str(tmp_path), mode="auto",
                       runner=lambda cmd, root: (True, "[exit 0]"))


def _assistant(session) -> list:
    return [e.content for e in session.ledger.entries if e.kind == "assistant"]


def test_chunks_arrive_in_order_before_the_reply_is_recorded(tmp_path):
    session = _session(tmp_path, StreamScript(REPLIES))
    log, replies = [], [[]]

    def chunk(piece):
        log.append(("chunk", len(_assistant(session))))
        replies[-1].append(piece)

    def end(text):
        log.append(("end", len(_assistant(session))))
        replies.append([])
    with streamed_send(session.agent, chunk, end):
        result = session.turn("write a note")
    joined = ["".join(parts) for parts in replies[:-1]]
    assert joined == REPLIES                       # in order, nothing lost or repeated
    assert _assistant(session) == joined           # the record is the joined chunks
    assert result.final == joined[-1]
    assert len(replies[0]) > 3                     # delivered in pieces, not at once
    first = [recorded for kind, recorded in log if kind == "chunk"][:len(replies[0])]
    assert set(first) == {0}                       # every chunk came before the entry
    assert [kind for kind, _ in log].index("end") == len(replies[0])
    assert session.ledger.verify()


def test_a_streamed_turn_records_what_a_plain_turn_records(tmp_path):
    plain = _session(tmp_path / "a", Script(REPLIES))
    streamed = _session(tmp_path / "b", StreamScript(REPLIES))
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir(exist_ok=True)
    first = plain.turn("write a note")
    with streamed_send(streamed.agent, lambda piece: None):
        second = streamed.turn("write a note")

    def shape(session):
        return [(e.kind, e.content, sorted(e.meta or {})) for e in session.ledger.entries
                if e.kind in ("user", "assistant", "tool_call", "tool_result", "approval")]
    assert shape(plain) == shape(streamed)
    assert [e.kind for e in plain.ledger.entries] == [e.kind for e in streamed.ledger.entries]
    assert first.final == second.final and first.steps == second.steps
    assert (tmp_path / "a" / "n.txt").read_text() == (tmp_path / "b" / "n.txt").read_text() == "hi"
    assert plain.agent.history == streamed.agent.history


def test_send_is_put_back_and_a_backend_that_cannot_stream_is_left_alone(tmp_path):
    backend = Script(REPLIES)
    session = _session(tmp_path, backend)
    send, chunks = session.agent.send, []
    with streamed_send(session.agent, chunks.append):
        assert "chat" not in vars(backend) and session.agent.send is send
        result = session.turn("write a note")
    assert chunks == [] and result.final == REPLIES[-1]
    streaming = StreamScript(REPLIES)
    with streamed_send(build_agent([streaming]), chunks.append):
        assert "chat" in vars(streaming)
    assert "chat" not in vars(streaming)


def test_streaming_never_changes_which_backend_answers(tmp_path):
    first, second = Script(["from the first"]), StreamScript(["from the second"])
    session = new_session(build_agent([first, second]), str(tmp_path), mode="auto",
                          runner=lambda cmd, root: (True, "[exit 0]"))
    chunks = []
    with streamed_send(session.agent, chunks.append):
        result = session.turn("hello")
    assert result.final == "from the first" and chunks == []


def test_a_stream_that_drops_falls_back_to_a_plain_reply_once(tmp_path):
    backend = StreamScript(["a reply long enough to arrive in several pieces"], fail_after=2)
    session = _session(tmp_path, backend)
    chunks, ends = [], []
    with streamed_send(session.agent, chunks.append, ends.append):
        result = session.turn("hello")
    assert len(chunks) == 2 and ends == [None]
    assert result.final == "a reply long enough to arrive in several pieces"
    assert _assistant(session) == [result.final]
    assert [m["role"] for m in session.agent.history] == ["user", "assistant"]


def test_the_line_gate_hides_tool_lines_and_passes_the_rest_at_once():
    shown = []
    gate = LineGate(shown.append)
    gate.feed("He")
    assert "".join(shown) == "He"                  # ordinary text is not held back
    for piece in ("llo.\nTO", 'OL run {"cmd": "ls"}\nTO', "DAY is fine\nTOOL x {}"):
        gate.feed(piece)
    gate.end()
    assert "".join(shown) == "Hello.\nTODAY is fine\n"
    gate.feed("no newline")
    gate.end()
    assert "".join(shown).endswith("no newline\n")


def test_indented_output_survives_any_chunk_boundary():
    out = []
    write = Indented(out.append)
    for piece in ("on", "e\ntw", "o\n", "three"):
        write("stdout", piece)
    assert "".join(out) == "    | one\n    | two\n    | three"


def test_a_live_turn_shows_text_once_and_hides_the_tool_line(tmp_path):
    session = _session(tmp_path, StreamScript(REPLIES))
    out, err = io.StringIO(), io.StringIO()
    with live(session, out, err):
        result = session.turn("write a note")
        assert session.streamed_final == result.final
    assert out.getvalue() == "I will write the note.\nWrote n.txt.\nNothing else changed.\n"


def test_run_turn_prints_the_final_answer_only_when_it_was_not_streamed(tmp_path, capsys):
    session = _session(tmp_path, StreamScript(REPLIES))
    with live(session):
        cli.run_turn(session, "write a note")
    assert capsys.readouterr().out.count("Nothing else changed.") == 1
    plain = _session(tmp_path, Script(["Plain answer."]))
    with live(plain):
        cli.run_turn(plain, "hello")
    assert capsys.readouterr().out == "Plain answer.\n"


def test_streaming_is_off_for_screen_readers_and_on_request(tmp_path, monkeypatch, capsys):
    assert cli.streaming_on()
    monkeypatch.setenv("FLYWHEEL_STREAM", "0")
    assert not cli.streaming_on()
    monkeypatch.delenv("FLYWHEEL_STREAM")
    monkeypatch.setenv("FLYWHEEL_SCREEN_READER", "1")
    assert not cli.streaming_on()
    backend = StreamScript(["Whole answer."])
    session = _session(tmp_path, backend)
    with live(session, enabled=False):
        assert "chat" not in vars(backend)
        cli.run_turn(session, "hello")
    assert capsys.readouterr().out == "Whole answer.\n"


def _sandbox_reason() -> str:
    if os.name == "nt":
        return ""
    from harness import safe_program
    from harness.posix_sandbox import PROGRAM, backend_for
    from harness.sandbox_probe import sandbox_starts
    backend = backend_for()
    if backend is None:
        return "no bubblewrap or Seatbelt on this host"
    found = safe_program.which(PROGRAM[backend])
    ready = sandbox_starts(backend, found if isinstance(found, str) else PROGRAM[backend])
    return "" if ready else f"{backend} will not start on this host"


@pytest.mark.skipif(bool(_sandbox_reason()), reason=_sandbox_reason() or "-")
def test_command_output_arrives_while_the_command_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "state"))
    root = tmp_path / "proj"
    root.mkdir()
    cmd = "echo one& ping -n 3 127.0.0.1 >nul & echo two" if os.name == "nt" \
        else "echo one; sleep 2; echo two"
    run, seen = cli._runner(), []
    quiet = run(cmd, str(root))
    run.sink = lambda stream, text: seen.append((time.monotonic(), stream, text))
    started = time.monotonic()
    loud = run(cmd, str(root))
    finished = time.monotonic()
    assert loud == quiet and loud[0]               # the record is the same either way
    text = "".join(piece for _, stream, piece in seen if stream == "stdout")
    assert text.split() == ["one", "two"]
    assert [line for line in loud[1].splitlines() if line in ("one", "two")] == text.split()
    assert seen[0][2].strip() == "one"
    assert seen[0][0] - started < (finished - started) - 0.8   # shown well before the end


def test_a_tail_reads_what_is_left_when_the_command_ends(tmp_path):
    seen = []
    done = OutputTail(lambda stream, text: seen.append((stream, text))).hook(tmp_path)
    (tmp_path / "stdout.txt").write_bytes("café one\n".encode("utf-8"))
    (tmp_path / "stderr.txt").write_bytes(b"warn\n")
    done()
    assert ("stdout", "café one\n") in seen and ("stderr", "warn\n") in seen
    assert "".join(text for stream, text in seen if stream == "stdout") == "café one\n"
