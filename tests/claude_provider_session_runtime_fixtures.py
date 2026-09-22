import hashlib
import json
import queue
import threading


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
        self.close_calls = []

    def close(self, *, timeout_s=2.0):
        self.close_calls.append(timeout_s)
        self.stdin.close()
        self.stdout.close()
        self.stderr.close()
        return type("Cleanup", (), {
            "exited": True,
            "job_closed": True,
            "stderr_drain_complete": True,
        })()


class IncompleteCleanupProcess(FakeProcess):
    def __init__(self, *, missing_stdout=False):
        super().__init__()
        self.stdout = None if missing_stdout else self.stdout
        self.close_calls = 0

    def close(self, *, timeout_s=2.0):
        self.close_calls += 1
        complete = self.close_calls > 1
        return type("Cleanup", (), {
            "exited": complete,
            "job_closed": complete,
            "stderr_drain_complete": complete,
        })()


class CapturingLauncher:
    def __init__(self, process):
        self.process = process
        self.calls = []

    def __call__(self, argv, cwd, env):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env)})
        threading.Thread(target=self._initialize_after_first_write, daemon=True).start()
        return self.process

    def _initialize_after_first_write(self):
        self.process.stdin.wait_messages(1)
        self.process.stdout.push({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": "flywheel-init-1",
                "response": {"current_permission_mode": "manual"},
            },
        })


class PassiveLauncher:
    def __init__(self, process):
        self.process = process
        self.calls = []

    def __call__(self, argv, cwd, env):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env)})
        return self.process


def runtime_fixture(tmp_path):
    state = tmp_path / "state"
    workspace = tmp_path / "workspace"
    auth = tmp_path / "auth"
    for path in (state, workspace, auth):
        path.mkdir()
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"owned claude launcher")
    digest = hashlib.sha256(b"owned claude launcher").hexdigest()
    return state, workspace, auth, executable, digest
