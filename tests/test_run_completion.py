"""A finished run separates what a check confirmed from what the model claimed."""
import copy
import hashlib
import time
from pathlib import Path

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_completion_outcome import derive_completion
from harness.gateway_operation import GatewayOperationError, canonicalize_operation
from harness.local_session import SessionLedger
from harness.plan_run_snapshot import thaw_json
from harness.run_completion import completion_report
from tests.test_gateway_operations import JOURNEY, OWNER
from tests.test_gateway_operation_recovery import OPERATION

WRITE = 'TOOL write_file {"path": "notes.md", "content": "hello"}'
HELLO = hashlib.sha256(b"hello").hexdigest()


def _operation(tmp_path, **extra):
    return {"goal": "write notes", "endpoint": "ollama", "model": "qwen2.5-coder:14b",
            "root": str(tmp_path), "max_steps": 4, "allow_write": True,
            "allow_exec": False, "stream": True, "data_refs": [],
            "credential_refs": [], **extra}


def _run(tmp_path, monkeypatch, replies, runner=None, **extra):
    """The real router path; the provider and, when given, the test runner are synthetic."""
    sent = []

    def factory(**authority):
        def transport(method, url, headers, body, timeout):
            sent.append(1)
            text = replies[min(len(sent), len(replies)) - 1]
            return 200, {"model": authority["model"],
                         "choices": [{"message": {"content": text}}]}
        return transport
    monkeypatch.setattr("harness.gateway_agent_transport.BoundAgentTransport", factory)
    if runner is not None:
        monkeypatch.setattr("harness.router_agent.make_sandboxed_runner",
                            lambda **kwargs: runner)
    op = _operation(tmp_path, **extra)
    binding = thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    error = None
    try:
        run_private_agent(op, {}, tmp_path, trace, None, lambda e: None,
                          binding=binding, deadline=time.monotonic() + 60)
    except GatewayOperationError as exc:
        error = exc
    records = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION).read()
    return error, records, records[-1]["payload"]["completion"]


def _statuses(report):
    return [(i["kind"], i["status"], i["check"]) for i in report["items"]]


def test_a_written_file_is_verified_and_an_unchecked_answer_stays_claimed(
        tmp_path, monkeypatch):
    error, records, report = _run(tmp_path, monkeypatch,
                                  [WRITE, "Created notes.md. Everything works now."])
    assert error is None
    assert _statuses(report) == [("file", "verified", "file_hash_recheck"),
                                 ("final_answer", "claimed", None)]
    assert report["verdict"] == "claimed" and report["unbacked_success_claim"] is True
    projected = derive_completion(records, "completed")
    assert projected["verdict"] == "claimed"
    assert projected["counts"] == {"verified": 1, "claimed": 1, "failed": 0}
    assert "notes.md" not in str(projected)


def test_a_passing_check_command_verifies_the_answer(tmp_path, monkeypatch):
    error, records, report = _run(
        tmp_path, monkeypatch, [WRITE, "Created notes.md."],
        runner=lambda cmd, root: (True, "3 passed"), test_cmd="pytest -q",
        allow_exec=True)
    assert error is None and report["verdict"] == "verified"
    assert _statuses(report)[-1] == ("final_answer", "verified", "test_command")
    assert derive_completion(records, "completed")["verdict"] == "verified"


def test_a_check_that_exits_zero_on_a_rate_limit_does_not_verify(tmp_path, monkeypatch):
    _, _, report = _run(
        tmp_path, monkeypatch, [WRITE, "Created notes.md."],
        runner=lambda cmd, root: (True, "Error: 429 Too Many Requests"),
        test_cmd="pytest -q", allow_exec=True, max_steps=2)
    assert report["items"][-1]["status"] == "failed"
    assert report["verdict"] == "failed"


def test_a_file_removed_after_it_was_written_fails(tmp_path, monkeypatch):
    def runner(cmd, root):
        (Path(root) / "notes.md").unlink()
        return True, "ok"
    _, _, report = _run(tmp_path, monkeypatch, [WRITE, "Created notes.md."],
                        runner=runner, test_cmd="cleanup", allow_exec=True)
    assert report["items"][0]["status"] == "failed"
    assert report["items"][0]["detail"] == "missing"
    assert report["verdict"] == "failed"


def test_a_stopped_run_still_rechecks_what_it_wrote(tmp_path, monkeypatch):
    error, records, report = _run(tmp_path, monkeypatch, [WRITE],
                                  run_budget={"max_tool_actions": 1})
    assert error.code == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert records[-1]["kind"] == "failure"
    assert _statuses(report) == [("file", "verified", "file_hash_recheck"),
                                 ("final_answer", "failed", "run_state")]
    assert report["items"][-1]["detail"] == "AGENT_RUN_BUDGET_EXHAUSTED"
    assert derive_completion(records, "failed")["verdict"] == "failed"


def test_report_sorting_without_a_run(tmp_path):
    ledger = SessionLedger()
    ledger.append("tool_call", 'write_file {"path": "a.txt"}')
    ledger.append("tool_result", "ok", {"tool": "write_file", "ok": True,
                                        "edited": {"a.txt": HELLO}})
    (tmp_path / "a.txt").write_text("changed", encoding="utf-8")
    report = completion_report(ledger.entries, {"final": "done"}, tmp_path)
    assert report["items"][0]["detail"] == "changed_after_write"
    events = [{"type": "cli_tool_call", "call_id": "w", "tool": "Write",
               "arguments": {"file_path": "b.txt", "content": "hello"}},
              {"type": "cli_tool_call", "call_id": "e", "tool": "Edit",
               "arguments": {"file_path": "c.txt", "old_string": "x"}}]
    (tmp_path / "b.txt").write_text("hello", encoding="utf-8")
    cli = completion_report([], {"final": "done"}, tmp_path, cli_events=events)
    assert [(i["path"], i["status"]) for i in cli["items"][:-1]] == [
        ("b.txt", "verified"), ("c.txt", "claimed")]


def _tampered(records, change):
    rows = copy.deepcopy(records)
    change(rows[-1]["payload"]["completion"])
    return rows


def test_the_gateway_refuses_a_completion_record_the_trace_does_not_support(
        tmp_path, monkeypatch):
    _, records, _ = _run(tmp_path, monkeypatch, [WRITE, "Created notes.md."],
                         runner=lambda cmd, root: (True, "3 passed"),
                         test_cmd="pytest -q", allow_exec=True)

    def omit(report):
        report["items"] = report["items"][1:]
        report["counts"]["verified"] -= 1
    assert derive_completion(_tampered(records, omit), "completed") == {
        "status": "unverifiable", "reason": "COMPLETION_OMITS_WRITE"}

    def forge_hash(report):
        report["items"][0]["observed_sha256"] = "0" * 64
    assert derive_completion(_tampered(records, forge_hash), "completed")["reason"] \
        == "COMPLETION_ITEM_NOT_SUPPORTED"

    no_test = [r for r in records if not (r["kind"] == "ledger" and
                                          r["payload"]["meta"].get("gate") == "test")]
    assert derive_completion(no_test, "completed")["reason"] == "COMPLETION_TEST_NOT_IN_TRACE"
    assert derive_completion(records, "failed")["reason"] \
        == "COMPLETION_VERIFIED_ON_FAILED_RUN"
