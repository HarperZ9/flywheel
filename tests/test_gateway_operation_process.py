from dataclasses import replace
import json
import os
import sys
import threading
import time
import pytest
import harness.gateway_operation_process as worker_protocol
from harness.cross_harness_process import ProcessOutcome, start_owned_process
from harness.gateway_operation import AuthorizedOperation, thaw_operation
from harness.gateway_operation_process import (
    GatewayAgentProcessFactory, GatewayWorker, WorkerOutcome,
)
from harness.gateway_provider_adapter import ExecutionPlan

SECRET = "synthetic-private-marker-419872"
ESCAPED_SECRET = 'synthetic\n"private"\\marker-572914'

def _strings(value):
    if type(value) is str: yield value
    elif type(value) is dict:
        for key, item in value.items(): yield from _strings(key); yield from _strings(item)
    elif type(value) is list:
        for item in value: yield from _strings(item)

class Tree:
    def __init__(self, stdout):
        self.stdout, self.resumed, self.signals = stdout, False, 0
    def resume(self): self.resumed = True; return True
    def signal_tree(self): self.signals += 1; return True
    def wait(self, _timeout):
        return ProcessOutcome(0, self.stdout, "", 1, False)
    def close(self): self.signal_tree()

def _authorized(tmp_path, secret=SECRET):
    operation = {"goal": "inspect", "endpoint": "local", "max_steps": 2,
                 "allow_write": False, "allow_exec": False, "stream": True,
                 "root": "workspace", "data_refs": [],
                 "credential_refs": ["cred_" + "a" * 32]}
    base = AuthorizedOperation.for_test(
        action="agent.run", operation=operation,
        scopes=("network", "secrets"))
    return replace(
        base, execution_plan=ExecutionPlan(
            "a" * 64, ("TOKEN",), ("cred_" + "a" * 32,)),
        credential_bindings={"TOKEN": secret})

def test_worker_launch_is_suspended_private_pipe_minimal_env_and_bounded(tmp_path):
    captures = []
    terminal = json.dumps({"type": "terminal", "state": "completed",
                           "result": {"final": "answer"}})
    def launch(spec):
        captures.append(spec)
        return Tree(terminal)
    progress = []
    authorized = _authorized(tmp_path)
    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path, launcher=launch).create(
            authorized, progress.append)
    assert worker.resume() is True
    outcome = worker.wait(1)
    spec = captures.single if hasattr(captures, "single") else captures[0]
    assert spec.shell is False and spec.suspended is True
    assert SECRET not in repr(authorized) and SECRET not in repr(spec)
    assert SECRET not in repr(spec.argv) and SECRET not in repr(spec.env)
    assert SECRET in spec.stdin_bytes.decode()
    assert set(spec.env) <= {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
                             "PATH", "TEMP", "TMP", "PYTHONPATH"}
    assert outcome.state == "completed" and outcome.result == {"final": "answer"}
    assert progress == []

@pytest.mark.parametrize(("secret", "stdout"), [
    (SECRET, "not-json"),
    (SECRET, json.dumps({"type": "terminal", "state": "completed",
                         "result": {"value": SECRET}})),
    (ESCAPED_SECRET, json.dumps({"type": "terminal", "state": "completed",
                                 "result": {"value": ESCAPED_SECRET}})),
    (ESCAPED_SECRET, "\n".join((json.dumps({"type": "progress", "event": {
        "value": ESCAPED_SECRET}}), json.dumps({"type": "terminal",
        "state": "completed", "result": {"final": "safe"}})))),
    (SECRET, "x" * ((1 << 20) + 1)),
], ids=("malformed", "secret", "escaped-result", "escaped-progress", "overflow"))
def test_malformed_overflow_or_secret_worker_output_fails_closed(
        tmp_path, secret, stdout):
    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path,
        launcher=lambda _spec: Tree(stdout)).create(
            _authorized(tmp_path, secret), lambda _event: None)
    worker.resume()
    outcome = worker.wait(1)
    assert outcome.state == "failed"
    assert outcome.result == {"reason": "EXTERNAL_ACTION_FAILED"}
    assert secret not in tuple(_strings(outcome.result))

def test_escaped_secret_is_absent_from_durable_stream_and_all_artifacts(
        tmp_path, caplog):
    from harness.gateway_operation_route import _stream
    from harness.gateway_operations import GatewayOperations, start_operation
    from harness.journey_store import JourneyStore, MutationCommand
    authorized = _authorized(tmp_path, ESCAPED_SECRET)
    head = JourneyStore(tmp_path).create(MutationCommand(
        authorized.owner_ref, authorized.journey_ref, None, "genesis", "intake",
        {"legacy_label": None, "goal": "secret boundary", "intake": {},
         "occurred_at": "2026-08-16T12:00:00Z"})).event_head_sha256
    authorized = replace(authorized, expected_event_head=head)
    class MaliciousWorker:
        control_class = "windows_job_v1"
        def __init__(self, progress): self.progress = progress
        def resume(self): return True
        def signal_tree(self): return True
        def close(self): pass
        def wait(self, _timeout):
            try: self.progress({"text": ESCAPED_SECRET})
            except Exception: pass
            return WorkerOutcome("completed", {"final": ESCAPED_SECRET})
    factory = type("F", (), {"create": lambda _self, _auth, progress:
                             MaliciousWorker(progress)})()
    service = GatewayOperations(
        tmp_path, clock=lambda: "2026-08-16T12:00:00Z")
    queued = start_operation(
        authorized=authorized, service=service, process_factory=factory)
    snapshot = service.wait_terminal(
        authorized.owner_ref, queued.operation_ref, 2)
    history = service._history(
        service._journey(authorized.owner_ref), queued.operation_ref)
    result = service.result(authorized.owner_ref, queued.operation_ref)
    wire = b"".join(_stream(
        service, authorized.owner_ref, queued.operation_ref, snapshot))
    artifacts = [json.loads(path.read_bytes()) for path in tmp_path.rglob("*.json")]
    surfaces = [history, result, caplog.text, *artifacts]
    assert all(ESCAPED_SECRET not in item for value in surfaces
               for item in _strings(value))
    assert ESCAPED_SECRET.encode() not in wire
    assert result["state"] == "failed"

def test_concurrent_wait_decodes_one_worker_outcome_once():
    terminal = "\n".join((
        json.dumps({"type": "progress", "event": {"step": 1}}),
        json.dumps({"type": "terminal", "state": "completed",
                    "result": {"final": "answer"}}),
    ))
    class SlowTree(Tree):
        def __init__(self):
            super().__init__(terminal)
            self.waits = 0
        def wait(self, timeout):
            self.waits += 1
            time.sleep(.1)
            return super().wait(timeout)
    tree, progress, outcomes = SlowTree(), [], []
    worker = GatewayWorker(tree, progress.append, ())
    threads = [threading.Thread(target=lambda: outcomes.append(worker.wait(1)))
               for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(1)
    assert tree.waits == 1 and len(outcomes) == 2
    assert outcomes[0] == outcomes[1]
    assert progress == [{"step": 1}]
@pytest.mark.parametrize("mode", ("result", "progress", "failure"))
def test_review_critical_child_secret_leak_writes_no_artifact(
        monkeypatch, tmp_path, mode):
    run_root, emitted = tmp_path / "runs", []
    (tmp_path / "workspace").mkdir()
    operation = thaw_operation(_authorized(tmp_path, ESCAPED_SECRET).operation)
    operation["root"] = str(tmp_path / "workspace")
    def leaking_run(*_args, on_event, **_kwargs):
        if mode != "result": on_event({"type": "assistant", "text": ESCAPED_SECRET})
        if mode == "failure": raise RuntimeError(ESCAPED_SECRET)
        return {"final": ESCAPED_SECRET if mode == "result" else "safe"}
    monkeypatch.setattr("harness.router_agent.run_router_agent", leaking_run)
    monkeypatch.setattr(worker_protocol, "_emit", emitted.append)
    monkeypatch.setattr(worker_protocol, "_worker_request", lambda: (
        operation, {"TOKEN": ESCAPED_SECRET}, tmp_path, run_root))
    assert worker_protocol._main() == 1
    assert emitted == [{"type": "terminal", "state": "failed",
                        "result": {"reason": "EXTERNAL_ACTION_FAILED"}}]
    artifacts = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert artifacts == []
@pytest.mark.parametrize(("stderr", "malformed", "expected"), (
    ("", False, "completed"), (SECRET, False, "cancelled"),
    ("", True, "cancelled")), ids=("natural", "secret-stderr", "malformed"))
def test_review_w2_final_drain_requires_wholly_valid_outcome(
        stderr, malformed, expected):
    killed = Tree("")
    killed.wait = lambda _timeout: ProcessOutcome(-1, "", "", 1, False, True)
    worker = GatewayWorker(killed, lambda _event: None, ())
    assert worker.signal_tree() is True
    assert worker.wait(1).state == "cancelled"
    terminal = json.dumps({"type": "terminal", "state": "completed",
                           "result": {"final": "natural"}}) + "\n"
    class Natural(Tree):
        def __init__(self): super().__init__(terminal); self.killed = False
        def stdout_snapshot(self): return b"", False
        def signal_tree(self): self.killed = True; return True
        def wait(self, _timeout):
            return (ProcessOutcome(-1, terminal, stderr, 1, False, malformed)
                    if self.killed else None)
    natural = Natural()
    worker = GatewayWorker(natural, lambda _event: None, (SECRET,))
    assert worker.wait(0) is None
    assert worker.signal_tree() is True
    assert worker.wait(1).state == expected


def test_review_w3_terminal_retry_keeps_exact_worker_outcome(tmp_path):
    class Immediate:
        control_class = "windows_job_v1"
        def resume(self): return True
        def signal_tree(self): return True
        def wait(self, _timeout):
            return WorkerOutcome("completed", {"final": "answer"})
        def close(self): pass
    attempts = []
    def commit(outcome):
        attempts.append(outcome)
        if len(attempts) == 1: raise OSError("commit window")
    worker_protocol.supervise_operation(
        authorized=_authorized(tmp_path),
        factory=type("F", (), {"create": lambda *_: Immediate()})(),
        progress=lambda _event: None, started=lambda _control: None,
        registered=lambda _worker: None, terminal=commit)
    assert [attempt.state for attempt in attempts] == ["completed", "completed"]
    assert attempts[0] == attempts[1]


def test_review_w6_progress_is_published_before_worker_exit():
    progress_line = json.dumps(
        {"type": "progress", "event": {"step": 1}}) + "\n"
    terminal_line = json.dumps(
        {"type": "terminal", "state": "completed",
         "result": {"final": "answer"}}) + "\n"
    class Incremental(Tree):
        def __init__(self):
            super().__init__("")
            self.release, self.visible = threading.Event(), progress_line
        def stdout_snapshot(self): return self.visible.encode(), False
        def wait(self, timeout):
            if not self.release.wait(min(timeout, .02)): return None
            self.stdout = self.visible + terminal_line
            return ProcessOutcome(0, self.stdout, "", 1, False)
    tree, progress, seen, outcomes = Incremental(), [], threading.Event(), []
    worker = GatewayWorker(
        tree, lambda event: (progress.append(event), seen.set()), ())
    thread = threading.Thread(target=lambda: outcomes.append(worker.wait(1)))
    thread.start()
    try:
        assert seen.wait(.2) and thread.is_alive()
    finally:
        tree.release.set(); thread.join(1)
    assert progress == [{"step": 1}] and outcomes[0].state == "completed"


def test_review_w14_failed_run_persists_only_bounded_fixed_diagnostics(
        monkeypatch, tmp_path):
    run_root, emitted = tmp_path / "runs", []
    (tmp_path / "workspace").mkdir()
    operation = thaw_operation(_authorized(tmp_path, secret="safe").operation)
    operation["root"] = str(tmp_path / "workspace")
    def failed_run(*_args, on_event, **_kwargs):
        for index in range(205):
            on_event({"type": "assistant", "text": "safe" * 300,
                      "index": index})
        raise RuntimeError("private provider diagnostic")

    monkeypatch.setattr("harness.router_agent.run_router_agent", failed_run)
    monkeypatch.setattr(worker_protocol, "_emit", emitted.append)
    monkeypatch.setattr(worker_protocol, "_worker_request", lambda: (
        operation, {}, tmp_path, run_root))

    assert worker_protocol._main() == 1
    files = list((run_root / "agent_runs").glob("*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_bytes())
    assert stored["status"] == "FAILED"
    assert stored["failure"] == {"code": "EXTERNAL_ACTION_FAILED"}
    assert len(stored["events"]) == 201
    assert stored["events"][-1] == {"type": "truncated", "dropped": 5}
    assert "private provider diagnostic" not in repr(stored)
    assert emitted[-1]["result"] == {"reason": "EXTERNAL_ACTION_FAILED"}


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree boundary")
def test_windows_owned_process_closes_descendant_tree_without_late_marker(tmp_path):
    marker = tmp_path / "late-marker"
    child = tmp_path / "child.py"
    child.write_text(
        "import pathlib,subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'-c',"
        "'import pathlib,sys,time;time.sleep(2);pathlib.Path(sys.argv[1]).write_text(\\\"late\\\")',"
        "sys.argv[1]])\n"
        "time.sleep(20)\n", encoding="utf-8")
    tree = start_owned_process(
        [sys.executable, str(child), str(marker)], cwd=tmp_path,
        stdin_bytes=b"", env={"SYSTEMROOT": os.environ["SYSTEMROOT"],
                               "PATH": os.environ.get("PATH", "")})
    assert tree.suspended is True and tree.resume() is True
    assert tree.signal_tree() is True
    assert tree.wait(2) is not None
    time.sleep(2.2)
    assert not marker.exists()
