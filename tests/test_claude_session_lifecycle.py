import json
import queue
import threading

from harness.claude_session_client import ClaudeSessionClient
from harness.claude_session_transport import (
    ClaudeSessionLaunchConfig,
    ClaudeSessionTransport,
)


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()
        self.closed = False

    def push_raw(self, raw):
        self._lines.put(raw)

    def readline(self, limit=-1):
        return self._lines.get()

    def close(self):
        self.closed = True
        self._lines.put(b"")


class UnsupportedBoundedReadline:
    def __init__(self):
        self.unbounded_called = False

    def readline(self, *args):
        if args:
            raise TypeError("bounded readline unsupported")
        self.unbounded_called = True
        return b'{"type":"assistant","message":{"content":[]}}\n'

    def close(self):
        pass


class BlockingStdout:
    def __init__(self, wake_on_close=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False
        self.wake_on_close = wake_on_close

    def readline(self, limit=-1):
        self.started.set()
        self.release.wait()
        return b""

    def close(self):
        self.closed = True
        if self.wake_on_close:
            self.release.set()


class Outbound:
    def __init__(self):
        self._chunks = []
        self.closed = False

    def write(self, chunk):
        self._chunks.append(bytes(chunk))
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def messages(self):
        return [json.loads(chunk.decode("utf-8")) for chunk in self._chunks]


class FakeProcess:
    def __init__(self, *, wake_stdout_on_close):
        self.stdin = Outbound()
        self.stdout = BlockingStdout(wake_on_close=wake_stdout_on_close)
        self.stderr = Outbound()
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.stdout.close()

    def wait(self, timeout=None):
        return 0


def launcher_for(process):
    return lambda argv, cwd, env: process


def client_for(process):
    return ClaudeSessionClient(process, ClaudeSessionTransport(
        incoming=process.stdout, outgoing=process.stdin, default_timeout=0.05),
        initialized=True)


def make_transport(incoming=None, outgoing=None):
    incoming = incoming or Inbound()
    outgoing = outgoing or Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    return transport, incoming, outgoing


def test_invalid_utf8_frame_marks_recovery_without_reader_crash():
    transport, incoming, _outgoing = make_transport()

    incoming.push_raw(b"\xff\n")

    protocol_event = transport.pop_protocol_event(timeout=1.0)
    assert protocol_event is not None
    assert protocol_event.kind == "malformed_json"
    assert transport.needs_recovery() is True
    assert transport.wait_closed(timeout=1.0) is True


def test_stream_without_bounded_readline_is_rejected_before_unbounded_read():
    incoming = UnsupportedBoundedReadline()
    transport, _incoming, _outgoing = make_transport(incoming=incoming)

    protocol_event = transport.pop_protocol_event(timeout=1.0)

    assert protocol_event is not None
    assert protocol_event.kind == "read_error"
    assert incoming.unbounded_called is False
    assert transport.needs_recovery() is True


def test_transport_shutdown_reports_incomplete_when_reader_does_not_exit():
    incoming = BlockingStdout(wake_on_close=False)
    transport, _incoming, _outgoing = make_transport(incoming=incoming)
    assert incoming.started.wait(timeout=1.0)

    assert transport.shutdown(timeout=0.05) is False

    assert incoming.closed is True
    event = transport.pop_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "cleanup_incomplete"
    incoming.release.set()
    assert transport.wait_closed(timeout=1.0) is True


def test_client_cancel_and_kill_return_reader_cleanup_status():
    process = FakeProcess(wake_stdout_on_close=True)
    client = client_for(process)
    assert process.stdout.started.wait(timeout=1.0)
    assert client.cancel(wait_timeout=0.05) is True

    blocked = FakeProcess(wake_stdout_on_close=False)
    client = client_for(blocked)
    assert blocked.stdout.started.wait(timeout=1.0)
    assert client.kill(wait_timeout=0.05) is False
    event = client.next_protocol_event(timeout=1.0)
    assert event is not None
    assert event.kind == "cleanup_incomplete"
    blocked.stdout.release.set()
