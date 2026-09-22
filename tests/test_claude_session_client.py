import json
import queue
import threading

import pytest

from harness.claude_session_client import ClaudeSessionClient
from harness.claude_session_transport import ClaudeSessionLaunchConfig


class FakeStdout:
    def __init__(self):
        self._lines = queue.Queue()
        self.closed = False

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

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
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]


class FakeProcess:
    def __init__(self, waits_before_exit=0):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.terminated = False
        self.killed = False
        self.waits_before_exit = waits_before_exit
        self.wait_calls = 0
        self.returncode = None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.close()

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls <= self.waits_before_exit:
            raise TimeoutError("still running")
        self.returncode = 0 if not self.killed else self.returncode
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


def init_response():
    return {"type": "control_response", "response": {
        "subtype": "success", "request_id": "flywheel-init-1", "response": {}}}


def initialized_launcher(process):
    launcher = FakeLauncher(process)
    launcher.after_message(1, init_response())
    return launcher


def test_client_requires_injected_launcher_until_execution_policy_is_bound():
    with pytest.raises(ValueError) as caught:
        ClaudeSessionClient.start(ClaudeSessionLaunchConfig(executable="claude.exe"))

    assert "launcher" in str(caught.value)


def test_client_starts_streaming_process_and_sends_text_turn():
    process = FakeProcess()
    launcher = initialized_launcher(process)
    config = ClaudeSessionLaunchConfig(
        executable="claude.exe",
        working_directory="C:/work/project",
        permission_mode="manual",
        resume_session_id="5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c",
    )

    client = ClaudeSessionClient.start(config, launcher=launcher)
    process.stdout.push({"type": "system", "subtype": "init", "session_id": "s1"})
    client.send_text("Continue the analysis")

    assert launcher.calls == [{
        "argv": [
            "claude.exe",
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            "--input-format", "stream-json",
            "--permission-mode=manual",
            "--permission-prompt-tool", "stdio",
            "--resume=5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c",
            "--replay-user-messages",
        ],
        "cwd": "C:/work/project",
        "env": {},
    }]
    assert process.stdin.wait_messages(2)[1]["message"]["content"] == "Continue the analysis"
    assert client.next_event(timeout=1.0).session_id == "s1"
    assert client.session_id == "s1"


def test_client_cancel_closes_pipes_waits_then_kills_when_process_does_not_exit():
    process = FakeProcess(waits_before_exit=2)
    launcher = initialized_launcher(process)
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"), launcher=launcher)

    client.send_text("Start work")
    client.cancel(wait_timeout=0.01)

    assert process.stdin.closed is True
    assert process.terminated is True
    assert process.killed is True
    assert process.stdout.closed is True
    assert client.needs_recovery() is True

def test_client_cancel_cannot_claim_cleanup_without_process_wait_proof():
    process = FakeProcess()
    process.wait = None
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=initialized_launcher(process),
    )

    assert client.cancel(wait_timeout=0.01) is False
    assert process.terminated is True
    assert process.killed is True
    assert process.stdout.closed is True


class TimeoutlessWaitProcess(FakeProcess):
    def __init__(self):
        super().__init__()
        self.wait_args = []
        self.unbounded_wait_called = False

    def wait(self, timeout=None):
        self.wait_calls += 1
        self.wait_args.append(timeout)
        if timeout is not None:
            raise TypeError("bounded wait unsupported")
        self.unbounded_wait_called = True
        self.stdout.close()
        return 0


def test_client_cancel_rejects_timeoutless_wait_without_unbounded_fallback():
    process = TimeoutlessWaitProcess()
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=initialized_launcher(process),
    )

    assert client.cancel(wait_timeout=0.01) is False
    assert process.terminated is True
    assert process.killed is True
    assert process.unbounded_wait_called is False
    assert process.wait_args == [0.01, 0.01]

def test_client_kill_cannot_claim_cleanup_without_process_wait_proof():
    process = FakeProcess()
    process.wait = None
    client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=initialized_launcher(process),
    )

    assert client.kill(wait_timeout=0.01) is False
    assert process.killed is True
    assert process.stdout.closed is True


def test_client_releases_runtime_custody_after_cancel_or_kill_cleanup():
    released = []
    cancel_client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=initialized_launcher(FakeProcess()),
    )
    cancel_client._runtime_release = lambda: released.append("cancel")

    assert cancel_client.cancel(wait_timeout=0.01) is True
    assert released == ["cancel"]

    kill_client = ClaudeSessionClient.start(
        ClaudeSessionLaunchConfig(executable="claude.exe"),
        launcher=initialized_launcher(FakeProcess()),
    )
    kill_client._runtime_release = lambda: released.append("kill")

    assert kill_client.kill(wait_timeout=0.01) is True
    assert released == ["cancel", "kill"]

