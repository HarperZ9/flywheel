from dataclasses import replace
import json
import os
import shutil
import sys
import threading
import time

import pytest

from harness.cross_harness_process import ProcessOutcome, start_owned_process
from harness.gateway_operation import AuthorizedOperation
from harness.gateway_operation_process import GatewayAgentProcessFactory, GatewayWorker
from harness.gateway_provider_adapter import ExecutionPlan


SECRET = "synthetic-private-marker-419872"


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


@pytest.mark.parametrize("stdout", [
    "not-json",
    json.dumps({"type": "terminal", "state": "completed",
                "result": {"value": SECRET}}),
    "x" * ((1 << 20) + 1),
], ids=("malformed", "secret", "overflow"))
def test_malformed_overflow_or_secret_worker_output_fails_closed(tmp_path, stdout):
    worker = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path,
        launcher=lambda _spec: Tree(stdout)).create(
            _authorized(tmp_path), lambda _event: None)
    worker.resume()
    outcome = worker.wait(1)
    assert outcome.state == "failed"
    assert outcome.result == {"reason": "EXTERNAL_ACTION_FAILED"}
    assert SECRET not in repr(outcome)


def test_secret_is_absent_from_durable_stream_error_and_log_surfaces(
        tmp_path, caplog):
    from harness.gateway_operation_route import _stream
    from harness.gateway_operations import GatewayOperations, start_operation
    from harness.journey_store import JourneyStore, MutationCommand
    authorized = _authorized(tmp_path)
    head = JourneyStore(tmp_path).create(MutationCommand(
        authorized.owner_ref, authorized.journey_ref, None, "genesis", "intake",
        {"legacy_label": None, "goal": "secret boundary", "intake": {},
         "occurred_at": "2026-08-16T12:00:00Z"})).event_head_sha256
    authorized = replace(authorized, expected_event_head=head)
    terminal = json.dumps({"type": "terminal", "state": "completed",
                           "result": {"final": "answer"}})
    factory = GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path,
        launcher=lambda _spec: Tree(terminal))
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

    assert SECRET not in repr((authorized, history, result, wire, caplog.text))
    assert result["result"] == {"final": "answer"}


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
    import time
    time.sleep(2.2)
    assert not marker.exists()
