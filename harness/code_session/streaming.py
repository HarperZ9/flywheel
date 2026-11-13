"""streaming.py -- show model text and command output as they arrive.

Two things a person waits on in a session: the model writing its reply, and a
command running. Both used to appear only when finished. This module delivers
each as chunks while it happens and changes nothing about what is recorded:

  model text      `streamed_send` makes each backend that has `chat_stream`
                  answer `chat` by reading that stream. The agent's `send`
                  runs unchanged around it: the same failover, compaction,
                  receipt and ledger entry. The entry is the joined chunks.
  command output  `OutputTail` reads stdout.txt and stderr.txt in the
                  sandbox's scratch folder while the command runs. The
                  command's recorded output is still read by the sandbox
                  itself, from the same files, after the command ends.

Model text streams only from a backend that has `chat_stream`, and which
backend answers is decided by `send` exactly as before. Today that is the
Ollama backend; a hosted provider's reply still arrives whole. A streamed
reply carries no token counts, so `/cost` lists that call as uncounted.
"""
from __future__ import annotations

import codecs
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

POLL_SECONDS = 0.1
TOOL_PREFIX = "TOOL "


def _generation(backend, text: str, ref: str, max_tokens, temperature, seed) -> dict:
    """The dict a backend's `chat` returns, built from a finished stream."""
    from harness.local_agent import OllamaBackend, generation_config
    gen = {"text": text, "model_ref": ref, "seed": seed}
    if isinstance(backend, OllamaBackend):
        gen["generation_config"] = generation_config(backend, max_tokens, temperature, seed)
    return gen


def _streaming_chat(backend, on_chunk, finish):
    """A `chat` for `backend` that reads its `chat_stream`.

    A stream that fails part way is answered by the backend's ordinary `chat`,
    so a dropped stream costs a second request and never a different result.
    `finish(None)` is called first, so a display can say that what it showed
    so far is not the reply.
    """
    from harness.local_agent import BackendError, MalformedBackendOutput

    def chat(messages, *, system, max_tokens, temperature, seed):
        options = {"system": system, "max_tokens": max_tokens,
                   "temperature": temperature, "seed": seed}
        full, stream = "", iter(backend.chat_stream(messages, **options))
        while True:
            try:
                piece = next(stream)
            except StopIteration as completed:
                ref = completed.value
                break
            except BackendError:
                finish(None)
                return type(backend).chat(backend, messages, **options)
            full += piece
            on_chunk(piece)
        if not isinstance(ref, str) or not ref:
            finish(None)
            raise MalformedBackendOutput("streaming backend omitted validated model reference")
        finish(full)
        return _generation(backend, full, ref, max_tokens, temperature, seed)
    return chat


@contextmanager
def streamed_send(agent, on_chunk, on_end=None):
    """While open, a reply from a streaming backend reaches `on_chunk` in pieces.

    `on_end(text)` is called when a streamed reply is complete, and
    `on_end(None)` when a stream failed and the reply will arrive whole.
    `agent.send` itself is not replaced.
    """
    finish = on_end if on_end is not None else (lambda text: None)
    wrapped = [(b, vars(b).get("chat")) for b in agent.backends if hasattr(b, "chat_stream")]
    for backend, _own in wrapped:
        backend.chat = _streaming_chat(backend, on_chunk, finish)
    try:
        yield
    finally:
        for backend, own in wrapped:
            if own is not None:
                backend.chat = own
            else:
                vars(backend).pop("chat", None)


class LineGate:
    """Pass text through, holding back the lines that are tool calls.

    The model asks for a tool by writing a line that starts with `TOOL `. The
    session already prints each call in its own form, so the raw line is not
    shown. A line is held only while its first characters could still spell
    that prefix; every other character goes out the moment it arrives.
    """

    def __init__(self, write):
        self.write, self.line, self.open, self.last = write, "", False, ""

    def feed(self, piece: str) -> None:
        for ch in piece:
            self._char(ch)

    def _char(self, ch: str) -> None:
        if self.open:
            self._out(ch)
        else:
            self.line += ch
            if ch == "\n" or not TOOL_PREFIX.startswith(self.line[:len(TOOL_PREFIX)]):
                if not self.line.startswith(TOOL_PREFIX):
                    self._out(self.line)
                self.line, self.open = "", ch != "\n" and not self.line.startswith(TOOL_PREFIX)
            return
        if ch == "\n":
            self.open = False

    def _out(self, text: str) -> None:
        self.write(text)
        self.last = text[-1:] or self.last

    def end(self) -> None:
        """Finish the reply: write a held partial line and close the last line."""
        if self.line and not self.line.startswith(TOOL_PREFIX):
            self._out(self.line)
        if self.last not in ("", "\n"):
            self.write("\n")
        self.line, self.open, self.last = "", False, ""


class OutputTail:
    """Deliver a running command's output to `on_chunk(stream, text)`.

    `hook` is the `work_hook` for `sandboxed_run`. It starts a reader thread
    and returns the function the sandbox calls when the output files are
    complete, which reads what is left and stops the thread. Chunks keep the
    file's order within each stream. A failure to read is never raised into
    the run: the recorded output does not depend on this class.
    """

    NAMES = (("stdout", "stdout.txt"), ("stderr", "stderr.txt"))

    def __init__(self, on_chunk):
        self.on_chunk, self.error = on_chunk, ""

    def hook(self, work):
        stop, state = threading.Event(), {
            name: [Path(work) / file, 0, codecs.getincrementaldecoder("utf-8")("replace")]
            for name, file in self.NAMES}

        def loop():
            while not stop.wait(POLL_SECONDS):
                self._drain(state)
        thread = threading.Thread(target=loop, name="flywheel-output-tail", daemon=True)
        thread.start()

        def done():
            stop.set()
            thread.join(2.0)
            self._drain(state, final=True)
        return done

    def _drain(self, state: dict, final: bool = False) -> None:
        for name, slot in state.items():
            path, offset, decoder = slot
            try:
                with open(path, "rb") as handle:
                    handle.seek(offset)
                    data = handle.read()
            except OSError:
                continue
            slot[1] = offset + len(data)
            text = decoder.decode(data, final)
            if text:
                try:
                    self.on_chunk(name, text)
                except Exception as exc:   # a display error must not end the command
                    self.error = self.error or f"{type(exc).__name__}: {exc}"


class Indented:
    """Write chunks with each line indented, whatever the chunk boundaries."""

    def __init__(self, write, lead: str = "    | "):
        self.write, self.lead, self.fresh = write, lead, True

    def __call__(self, _stream: str, text: str) -> None:
        for line in text.splitlines(keepends=True):
            self.write((self.lead if self.fresh else "") + line)
            self.fresh = line.endswith("\n")


@contextmanager
def live(session, out=None, err=None, enabled: bool = True):
    """Stream one turn to the terminal: model text to `out`, commands to `err`.

    `session.streamed_final` holds the last reply that was shown in full, so
    the caller can skip printing the same answer a second time. With `enabled`
    False nothing is streamed and the turn prints as it always did.
    """
    session.streamed_final = None
    if not enabled:
        yield
        return
    out, err = out or sys.stdout, err or sys.stderr

    def put(stream):
        def write(text: str) -> None:
            stream.write(text)
            stream.flush()
        return write
    gate = LineGate(put(out))

    def ended(text) -> None:
        gate.end()
        if text is None:
            put(err)("[stream interrupted; the reply follows]\n")
        session.streamed_final = text
    runner = getattr(session.executor, "runner", None)
    tails = hasattr(runner, "sink")
    if tails:
        runner.sink = Indented(put(err))
    try:
        with streamed_send(session.agent, gate.feed, ended):
            yield
    finally:
        if tails:
            runner.sink = None
