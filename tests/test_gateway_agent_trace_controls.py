"""Failure, filesystem substitution, and actual owned-process controls."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from harness.cross_harness_process import start_owned_process
from harness.gateway_agent_execution import recovered_projection
from harness.gateway_agent_trace import AgentTrace, TraceError
from harness.gateway_operation_process import GatewayWorker
from tests.test_gateway_agent_execution import OWNER, JOURNEY, OP, MARKER, operation, run_bound


@pytest.mark.parametrize("raises", [False, True])
def test_actual_router_tool_result_and_exception_keep_marker_private(tmp_path, monkeypatch, raises):
    (tmp_path / "fixture.txt").write_text(MARKER + "x" * 1500 + "\nLAST-LINE")
    def transport_factory(**authority):
        calls = []
        def transport(method, url, headers, body, timeout):
            calls.append(json.loads(body))
            assert calls[-1]["model"] == authority["model"]
            text = 'TOOL read_file {"path":"fixture.txt"}' if len(calls) == 1 else MARKER
            return 200, {"model": authority["model"],
                "choices": [{"message": {"content": text}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", transport_factory)
    if raises:
        def fail(*args, **kwargs): raise RuntimeError(MARKER)
        monkeypatch.setattr("harness.local_tools.ToolExecutor.execute", fail)
    writer, emitted = AgentTrace(tmp_path, OWNER, JOURNEY, OP), []
    if raises:
        with pytest.raises(RuntimeError):
            run_bound(operation(tmp_path), {}, tmp_path, writer, emitted.append)
        result = writer.projection("failed", reason="EXTERNAL_ACTION_FAILED")
    else:
        result = run_bound(operation(tmp_path), {}, tmp_path, writer, emitted.append)
        tools = [r["payload"]["content"] for r in writer.read()
                 if r["kind"] == "ledger" and r["payload"]["kind"] == "tool_result"]
        assert len(tools) == 1 and MARKER in tools[0] and "LAST-LINE" in tools[0]
    assert MARKER not in json.dumps([result, emitted])


def test_progress_custody_failure_prevents_next_tool(tmp_path, monkeypatch):
    calls = []
    def transport_factory(**authority):
        def transport(method, url, headers, body, timeout):
            assert json.loads(body)["model"] == authority["model"]
            return 200, {"model": authority["model"], "choices": [{"message": {
                "content": 'TOOL read_file {"path":"fixture.txt"}'}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", transport_factory)
    monkeypatch.setattr("harness.local_tools.ToolExecutor.execute", lambda *a, **kw: calls.append(True))
    writer = AgentTrace(tmp_path, OWNER, JOURNEY, OP)
    append = writer.append
    def reject_progress(kind, payload):
        if kind == "progress": raise TraceError()
        return append(kind, payload)
    monkeypatch.setattr(writer, "append", reject_progress)
    with pytest.raises(TraceError):
        run_bound(operation(tmp_path), {}, tmp_path, writer, lambda _: None)
    assert calls == []


def test_root_replacement_after_admission_never_reads_other_tree(tmp_path, monkeypatch):
    import harness.gateway_agent_trace as module
    state = tmp_path / "state"; state.mkdir()
    writer = AgentTrace(state, OWNER, JOURNEY, OP)
    writer.append("request", {"goal": "original"})
    real_open = module.open_artifact_root
    @contextmanager
    def race(*args, **kwargs):
        with real_open(*args, **kwargs) as fs:
            try: state.rename(tmp_path / "old")
            except PermissionError: pass  # pinned Windows handles prohibit rename
            else: state.mkdir()
            yield fs
    monkeypatch.setattr(module, "open_artifact_root", race)
    try:
        records = writer.read()
        assert records[0]["payload"]["goal"] == "original"
    except TraceError:
        pass  # a POSIX ancestor substitution is explicitly unsafe


def test_trace_reparse_root_refused_without_opening_target(tmp_path):
    actual, alias = tmp_path / "actual", tmp_path / "alias"
    actual.mkdir()
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(actual)],
                       check=True, capture_output=True)
    else: alias.symlink_to(actual, target_is_directory=True)
    try:
        with pytest.raises(TraceError): AgentTrace(alias, OWNER, JOURNEY, OP)
        assert list(actual.iterdir()) == []
    finally:
        if os.name == "nt": alias.rmdir()
        else: alias.unlink()


@pytest.mark.skipif(os.name != "nt", reason="owned process control is Windows-only")
def test_actual_owned_child_cancel_preserves_private_prefix(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    code = "\n".join([
        "import sys,time", "from pathlib import Path",
        "from harness.gateway_agent_trace import AgentTrace,TraceLedger",
        f"trace=AgentTrace(Path(sys.argv[1]),{OWNER!r},{JOURNEY!r},{OP!r})",
        f"TraceLedger(trace).append('user',{MARKER!r})", "time.sleep(30)"])
    tree = start_owned_process([sys.executable, "-c", code, str(tmp_path)],
        cwd=repo, stdin_bytes=b"", env={"SYSTEMROOT": os.environ["SYSTEMROOT"],
            "PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
    worker = GatewayWorker(tree, lambda _: None, ())
    assert worker.resume()
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline and not list(tmp_path.rglob("head-*.json")):
            time.sleep(.02)
        assert list(tmp_path.rglob("head-*.json"))
        assert worker.signal_tree()
        assert worker.wait(2).state == "cancelled"
        projection = recovered_projection(tmp_path, OWNER, JOURNEY, OP, "cancelled")
        assert projection["record_count"] == 1 and MARKER not in json.dumps(projection)
        assert MARKER in AgentTrace(tmp_path, OWNER, JOURNEY, OP).read()[0]["payload"]["content"]
    finally: worker.close()


def test_cancel_winning_terminal_race_still_seals_private_trace_ref(tmp_path, monkeypatch):
    from tests.test_gateway_operations import (
        _service, _authorized, _cancel_raw, Process, Factory, OWNER as OWNER2, JOURNEY as JOURNEY2)
    from harness.gateway_operations import start_operation, cancel_operation
    process, service = Process(), _service(tmp_path)
    queued = start_operation(authorized=_authorized(tmp_path), service=service,
        process_factory=Factory(process, tmp_path))
    assert process.resumed.wait(10)
    trace = AgentTrace(tmp_path, OWNER2, JOURNEY2, queued.operation_ref)
    trace.append("request", {"goal": MARKER})
    release, caller = threading.Event(), threading.get_ident()
    original = service._terminal
    def terminal(*args, **kwargs):
        if threading.get_ident() != caller: release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "_terminal", terminal)
    try:
        snapshot = service.snapshot(OWNER2, queued.operation_ref)
        outcome = cancel_operation(action="operation.cancel",
            raw=_cancel_raw(snapshot, queued.operation_ref), owner_ref=OWNER2, service=service)
        assert outcome.state == "cancelled"
        result = service.result(OWNER2, queued.operation_ref)["result"]
        assert result["trace_ref"] == trace.ref and result["record_count"] == 1
        assert MARKER not in json.dumps(result)
    finally: release.set()
