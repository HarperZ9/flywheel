import json
import queue
import threading

import pytest

from harness.claude_session_client import ClaudeSessionClient
from harness.claude_session_transport import (
    ClaudeSessionLaunchConfig,
    ClaudeSessionTransport,
    ClaudeSessionTransportError,
    build_claude_session_argv,
)


class FakeStdout:
    def __init__(self):
        self._lines = queue.Queue()
        self.closed = False

    def push(self, message):
        self._lines.put(json.dumps(message, separators=(",", ":")).encode() + b"\n")

    def close(self):
        self.closed = True
        self._lines.put(b"")

    def readline(self, limit=-1):
        return self._lines.get()


class FakeStdin:
    def __init__(self):
        self._chunks = []
        self._condition = threading.Condition()
        self.closed = False

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
            chunks = list(self._chunks)
        return [json.loads(chunk.decode()) for chunk in chunks]


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.stderr = FakeStdout()
        self.terminated = False
        self.killed = False
        self.returncode = None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.close()

    def wait(self, timeout=None):
        self.returncode = 0 if self.returncode is None else self.returncode
        self.stdout.close()
        return self.returncode


class FakeLauncher:
    def __init__(self, process):
        self.process = process
        self.calls = []
        self.responders = []

    def after_message(self, count, message):
        self.responders.append((count, message))

    def __call__(self, argv, cwd, env):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env or {})})
        for count, message in self.responders:
            threading.Thread(
                target=lambda c=count, m=message: (
                    self.process.stdin.wait_messages(c), self.process.stdout.push(m)),
                daemon=True,
            ).start()
        return self.process


def response(request_id, *, subtype="success", body=None, error=""):
    data = {"subtype": subtype, "request_id": request_id}
    if subtype == "success":
        data["response"] = {} if body is None else body
    else:
        data["error"] = error
    return {"type": "control_response", "response": data}


def run_async(fn):
    box = {}
    def wrapped():
        try:
            box["result"] = fn()
        except BaseException as exc:
            box["error"] = exc
    thread = threading.Thread(target=wrapped, daemon=True)
    thread.start()
    return thread, box


def test_launch_config_defaults_to_manual_with_sdk_stdio_permission_custody():
    argv = build_claude_session_argv(ClaudeSessionLaunchConfig(executable="claude.exe"))

    assert "--permission-mode=manual" in argv
    assert argv[argv.index("--permission-prompt-tool") + 1] == "stdio"
    assert "--safe-mode" not in argv
    assert "--restricted" not in argv
    assert not any(item.startswith("--setting-sources") for item in argv)
    assert not any(item.startswith("--tools") for item in argv)


def test_launch_config_emits_no_generation_isolation_controls():
    argv = build_claude_session_argv(ClaudeSessionLaunchConfig(
        executable="claude.exe",
        safe_mode=True,
        restricted=True,
        setting_sources=(),
        tools=(),
    ))

    assert "--safe-mode" in argv
    assert "--restricted" in argv
    assert "--setting-sources=" in argv
    assert "--tools=" in argv
    assert "" not in argv


def test_transport_initialize_matches_success_and_ignores_wrong_response():
    incoming, outgoing = FakeStdout(), FakeStdin()
    transport = ClaudeSessionTransport(incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    thread, box = run_async(lambda: transport.initialize(timeout=0.5))

    assert outgoing.wait_messages(1)[0] == {
        "type": "control_request",
        "request_id": "flywheel-init-1",
        "request": {"subtype": "initialize", "hooks": None},
    }
    incoming.push(response("wrong", body={"ignored": True}))
    incoming.push(response("flywheel-init-1", body={"current_permission_mode": "manual"}))
    thread.join(1.0)

    assert box == {"result": {"current_permission_mode": "manual"}}
    assert transport.pop_protocol_event(timeout=1.0).kind == "unexpected_control_response"
    incoming.close()


def test_transport_initialize_timeout_and_error_are_bounded_and_redacted():
    incoming, outgoing = FakeStdout(), FakeStdin()
    timed = ClaudeSessionTransport(incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    with pytest.raises(ClaudeSessionTransportError) as timeout:
        timed.initialize(timeout=0.05)
    assert timeout.value.code == "control_response_timeout"
    incoming.close()

    incoming, outgoing = FakeStdout(), FakeStdin()
    failed = ClaudeSessionTransport(incoming=incoming, outgoing=outgoing, default_timeout=0.05)
    thread, box = run_async(lambda: failed.initialize(timeout=0.5))
    assert outgoing.wait_messages(1)[0]["request_id"] == "flywheel-init-1"
    incoming.push(response("flywheel-init-1", subtype="error", error="raw secret provider text"))
    thread.join(1.0)

    assert box["error"].code == "control_response_error"
    assert "raw secret" not in str(box["error"])
    incoming.close()


def test_client_start_initializes_before_user_input_and_client_blocks_uninitialized_input():
    process = FakeProcess()
    launcher = FakeLauncher(process)
    launcher.after_message(1, response("flywheel-init-1", body={"current_permission_mode": "manual"}))

    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=launcher,
        initialize_timeout=0.5,
    )
    client.send_text("after init")

    messages = process.stdin.wait_messages(2)
    assert messages[0]["request"]["subtype"] == "initialize"
    assert messages[1]["message"]["content"] == "after init"

    raw = ClaudeSessionClient(process, ClaudeSessionTransport(
        incoming=FakeStdout(), outgoing=FakeStdin(), default_timeout=0.05))
    with pytest.raises(ClaudeSessionTransportError) as caught:
        raw.send_text("too early")
    assert caught.value.code == "not_initialized"


def test_client_interrupt_uses_sdk_control_request_not_process_cancel():
    process = FakeProcess()
    launcher = FakeLauncher(process)
    launcher.after_message(1, response("flywheel-init-1"))
    launcher.after_message(2, response("flywheel-interrupt-2", body={"ok": True}))
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=launcher,
        initialize_timeout=0.5,
    )

    assert client.interrupt(timeout=0.5) == {"ok": True}
    messages = process.stdin.wait_messages(2)
    assert messages[1] == {
        "type": "control_request",
        "request_id": "flywheel-interrupt-2",
        "request": {"subtype": "interrupt"},
    }
    assert process.terminated is False
    assert process.killed is False


def test_client_interrupt_timeout_is_uncertain_without_process_cancel():
    process = FakeProcess()
    launcher = FakeLauncher(process)
    launcher.after_message(1, response("flywheel-init-1"))
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=launcher,
        initialize_timeout=0.5,
    )

    with pytest.raises(ClaudeSessionTransportError) as caught:
        client.interrupt(timeout=0.05)

    assert caught.value.code == "control_response_timeout"
    assert client.needs_recovery() is True
    assert process.terminated is False
    assert process.killed is False


def test_client_start_closes_owned_process_when_initialize_fails():
    class CloseOnlyProcess(FakeProcess):
        def __init__(self):
            super().__init__()
            self.close_calls = []

        def close(self, *, timeout_s=2.0):
            self.close_calls.append(timeout_s)
            self.stdout.close()
            self.stdin.close()
            self.stderr.close()

    process = CloseOnlyProcess()
    launcher = FakeLauncher(process)

    with pytest.raises(ClaudeSessionTransportError):
        ClaudeSessionClient.start(
            ClaudeSessionLaunchConfig(executable="claude.exe"),
            launcher=launcher,
            initialize_timeout=0.05,
        )

    assert process.close_calls == [0.05]
