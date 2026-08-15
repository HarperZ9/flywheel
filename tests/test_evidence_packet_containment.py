"""Terminal fail-closed boundary for arbitrary Python journey checks."""
import socket
import sys
from pathlib import Path

import pytest

import harness.oracle as oracle_module
from harness.evidence_journey import append_event, new_journey, run_journey_check
from harness.evidence_packet import pack_journey_packet, verify_journey_packet
from harness.execution_input_protection import ExecutionInputProtectionUnavailable
from harness.pytest_prepared import verify_prepared


REASON = "EXECUTION_CONTAINMENT_UNAVAILABLE"
LIMIT = ("NOT_PROVES_CANDIDATE_BEHAVIOR: candidate and tests were not executed "
         "because deny-read and deny-egress containment is unavailable.")
REQUIREMENT = {
    "schema": "flywheel.python-execution-containment-requirement/v1",
    "status": "UNAVAILABLE",
    "child_process_spawned": False,
    "candidate_spawned": False,
    "candidate_executed": False,
    "tests_executed": False,
    "required_runtime": {
        "identity": "Windows AppContainer/lowbox identity",
        "filesystem": "allowlisted staging ACL",
        "network": "no network capabilities",
    },
}


def _journey():
    journey = new_journey(journey_id="containment-v1", goal="Check Python",
        intake={"summary": "untrusted Python"}, created_at="2026-08-13T12:00:00Z")
    return append_event(journey, {"stage": "decomposed",
        "occurred_at": "2026-08-13T12:01:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The candidate meets its tests",
            "depends_on": [], "verdict": "UNDECIDED",
            "reason": "registered checker has not run", "receipt_refs": []}]})


def _listener():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0)); listener.listen(2); listener.settimeout(0.2)
    return listener, listener.getsockname()[1]


def _received(listener):
    try:
        connection, _ = listener.accept()
    except TimeoutError:
        return None
    with connection:
        connection.settimeout(0.2)
        return connection.recv(1024)


def _fixture(tmp_path, attempt):
    root = tmp_path / "artifacts"; root.mkdir()
    candidate, test = root / "candidate.py", root / "test_candidate.py"
    canary = tmp_path / "outside-canary.txt"; canary.write_text("outside-secret", encoding="utf-8")
    read_listener, read_port = _listener(); process_listener, process_port = _listener()
    child = ("import socket; s=socket.create_connection(('127.0.0.1',"
             f"{process_port}),timeout=2); s.sendall(b'process-spawned'); s.close()")
    prefix = ("from pathlib import Path\nimport socket, subprocess, sys\n"
        f"data=Path({str(canary)!r}).read_bytes()\n"
        f"s=socket.create_connection(('127.0.0.1',{read_port}),timeout=2); "
        "s.sendall(data); s.close()\n"
        f"subprocess.run([sys.executable,'-c',{child!r}],check=True,timeout=2)\n")
    implementations = {
        "benign": "def add(a,b): return a+b\n",
        "failing": "def add(a,b): return a-b\n",
        "collection-error": "def add(a,b): return a+b\n",
        "oversized-output": "print('x'*3000000)\ndef add(a,b): return a+b\n",
    }
    candidate.write_text(prefix + implementations[attempt], encoding="utf-8")
    test_source = ("import deliberately_missing_dependency\n" if attempt == "collection-error"
                   else "from candidate import add\ndef test_add(): assert add(2,3)==5\n")
    test.write_text(test_source, encoding="utf-8")
    context = {"task_id": "containment-v1", "prompt": "Check candidate",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "candidate.py",
        "raw_artifact_refs": ["candidate.py", "test_candidate.py"],
        "timeout_seconds": 15}
    return root, candidate, context, read_listener, process_listener


@pytest.mark.parametrize("attempt", [
    "benign", "failing", "collection-error", "oversized-output"])
def test_arbitrary_python_attempts_stop_before_any_child_execution(tmp_path, attempt):
    root, candidate, context, read_listener, process_listener = _fixture(tmp_path, attempt)
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
        leaked, spawned = _received(read_listener), _received(process_listener)
    finally:
        read_listener.close(); process_listener.close()
    assert leaked is None, leaked
    assert spawned is None, spawned
    assert (result["verdict"], result["unverifiable_reason"]) == ("UNVERIFIABLE", REASON)
    assert result["oracle_calls_consumed"] == 0
    assert (result["claim_id"], result["claim_verdict_before"]) == (
        "claim-root", "UNDECIDED")
    assert result["execution_containment"] == REQUIREMENT
    assert result["does_not_prove"] == [LIMIT]
    assert "receipt_ref" not in result and not (root / "receipts").exists()


def test_candidate_junit_parser_and_oracle_dispatch_are_unreachable(tmp_path, monkeypatch):
    root, candidate, context, first, second = _fixture(tmp_path, "benign")
    monkeypatch.setattr(oracle_module, "_pytest_canonical", lambda *_:
        (_ for _ in ()).throw(AssertionError("candidate JUnit parser reached")))
    monkeypatch.setattr(oracle_module.PytestOracle, "verify_prepared", lambda *_:
        (_ for _ in ()).throw(AssertionError("pytest oracle dispatch reached")))
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    finally:
        first.close(); second.close()
    assert result["unverifiable_reason"] == REASON
    assert "receipt_ref" not in result and not (root / "receipts").exists()


def test_python_refusal_does_not_even_resolve_or_open_candidate(tmp_path):
    """Candidate path admission before refusal would already grant a host read."""
    class UnreadablePath(type(Path())):
        def resolve(self, *args, **kwargs):
            raise AssertionError("candidate resolution reached")

        def open(self, *args, **kwargs):
            raise AssertionError("candidate open reached")

    candidate = UnreadablePath(tmp_path / "never-read.py")
    context = {
        "task_id": "containment-v1", "prompt": "Check candidate",
        "oracle_cmd": f'"{sys.executable}" -m pytest test_candidate.py',
        "candidate_ref": "never-read.py", "raw_artifact_refs": ["never-read.py"],
        "timeout_seconds": 15,
    }

    result = run_journey_check(_journey(), "claim-root", "code", candidate, context)

    assert result["unverifiable_reason"] == REASON
    assert result["oracle_calls_consumed"] == 0 and "receipt_ref" not in result


def test_retired_prepared_pytest_entry_refuses_before_using_inputs():
    entries = [lambda: verify_prepared(None, [], None, []),
               lambda: oracle_module.PytestOracle().verify_prepared([], None, [])]
    for entry in entries:
        with pytest.raises(ExecutionInputProtectionUnavailable, match=REASON):
            entry()


def test_an_unadmitted_python_run_cannot_be_packed_as_fail_or_pass(tmp_path):
    root, candidate, context, first, second = _fixture(tmp_path, "failing")
    try:
        result = run_journey_check(_journey(), "claim-root", "code", candidate, context)
    finally:
        first.close(); second.close()
    assert result["unverifiable_reason"] == REASON and "receipt_ref" not in result
    journey = append_event(_journey(), {"stage": "preflight",
        "occurred_at": "2026-08-13T12:02:00Z", "claims": [{
            "claim_id": "claim-root", "statement": "The candidate meets its tests",
            "depends_on": [], "verdict": "UNVERIFIABLE", "reason": REASON,
            "receipt_refs": [], "raw_artifact_refs": []}]})
    packet = tmp_path / "packet"
    with pytest.raises(ValueError, match="requires receipts and raw evidence"):
        pack_journey_packet(packet, journey=journey, artifact_root=root)
    assert not packet.exists()
    assert verify_journey_packet(packet)["verdict"] == "UNVERIFIABLE"
