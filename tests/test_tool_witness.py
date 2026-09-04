"""The tool surface witnesses its bytes, and the receipt names the same digest."""
from __future__ import annotations

import json
from pathlib import Path

from harness.action_witness import LOG_NAME, read_log, verify_log
from harness.byte_witness import witness_bytes
from harness.local_tools import ToolExecutor, ToolGate
from harness.tool_call_receipt import MATCH, UNVERIFIABLE
from harness.tool_witness import (RECEIPT_JSON, REPR, receipt_args_bytes,
                                  seal_call, witness_call)


def _executor(tmp_path, *, receipts=True):
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    (root / "hello.txt").write_text("hello world", encoding="utf-8")
    executor = ToolExecutor(
        root=str(root), gate=ToolGate(allow_write=False, allow_exec=False),
        receipt_dir=str(tmp_path / "receipts") if receipts else None)
    executor.init_receipt_chain("test-run")
    return executor


def _records(executor):
    return read_log(Path(executor.receipt_dir) / LOG_NAME)


def test_the_receipt_and_the_chain_name_one_digest(tmp_path):
    # The whole point of mirroring build_receipt's encoding. If either side
    # changes how it turns arguments into bytes, this is what says so.
    executor = _executor(tmp_path)
    executor.execute("read_file", {"path": "hello.txt"})
    receipt = json.loads(sorted(Path(executor.receipt_dir).glob("*.json"))[0]
                         .read_text(encoding="utf-8"))
    args_record, output_record = _records(executor)
    assert receipt["args"]["sha256"] == args_record["sha256"]
    assert receipt["args"]["bytes"] == args_record["length"]
    assert receipt["output"]["sha256"] == output_record["sha256"]
    assert receipt["output"]["bytes"] == output_record["length"]


def test_empty_arguments_agree_on_the_empty_digest(tmp_path):
    executor = _executor(tmp_path)
    executor.execute("list_dir", {})
    receipt = json.loads(sorted(Path(executor.receipt_dir).glob("*.json"))[0]
                         .read_text(encoding="utf-8"))
    assert receipt["args"]["sha256"] == _records(executor)[0]["sha256"]
    assert receipt["args"]["bytes"] == 0


def test_two_calls_leave_four_records_in_one_chain(tmp_path):
    executor = _executor(tmp_path)
    executor.execute("read_file", {"path": "hello.txt"})
    executor.execute("list_dir", {"path": "."})
    records = _records(executor)
    assert [r["context"]["kind"] for r in records] == [
        "input", "output", "input", "output"]
    assert [r["context"]["seq"] for r in records] == [1, 1, 2, 2]
    result = verify_log(records)
    assert result["verdict"] == UNVERIFIABLE      # the links held, the bytes went unasked
    assert result["checked"] == 4 and result["head"]


def test_the_chain_records_what_the_call_was_and_how_it_ended(tmp_path):
    executor = _executor(tmp_path)
    executor.execute("read_file", {"path": "nope.txt"})
    context = _records(executor)[0]["context"]
    assert context["action"] == "tool:read_file"
    assert context["capability"] == "builtin-read"
    assert (context["outcome"], context["ok"]) == ("ERROR", False)
    assert context["run_id"] == "test-run"


def test_a_blocked_call_is_witnessed_like_any_other(tmp_path):
    executor = _executor(tmp_path)
    result = executor.execute("run", {"cmd": "echo hi"})
    assert not result.ok
    assert _records(executor)[0]["context"]["outcome"] == "BLOCKED"


def test_the_witness_runs_with_no_receipt_directory(tmp_path):
    # The receipt directory is an opt-in. The chain is what the run did.
    executor = _executor(tmp_path, receipts=False)
    executor.execute("read_file", {"path": "hello.txt"})
    executor.execute("list_dir", {"path": "."})
    assert executor.action_witness_head()
    assert len(executor._action_log) == 4
    assert not executor.receipt_chain_head()


def test_a_head_is_empty_until_something_has_been_witnessed(tmp_path):
    executor = _executor(tmp_path, receipts=False)
    assert executor.action_witness_head() == ""
    executor.execute("read_file", {"path": "hello.txt"})
    assert executor.action_witness_head()


def test_arguments_no_encoder_will_take_are_still_witnessed():
    payload, encoding = receipt_args_bytes({"fn": object()})
    assert encoding == REPR and payload
    assert receipt_args_bytes({"path": "x"})[1] == RECEIPT_JSON
    assert receipt_args_bytes({}) == (b"", RECEIPT_JSON)


def test_a_call_with_no_chain_to_witness_onto_says_so():
    assert witness_call(None, tool="read_file", args={}, output="", ok=True,
                        seq=1) is None


def test_a_receipt_that_cannot_be_written_leaves_a_broken_chain(tmp_path):
    # emit_receipt swallows its own write failure, so the head advances over a
    # receipt no directory holds and the next one points at nothing. That is
    # the honest outcome: the chain reads as broken, never as complete.
    unwritable = tmp_path / "wall"
    unwritable.write_text("not a directory", encoding="utf-8")
    head = seal_call(unwritable, tool="read_file", capability="builtin-read",
                     admission="ALLOWED", args={"path": "x"}, output="", ok=True,
                     outcome="COMPLETED", run_id="r", seq=1, prev="a" * 64)
    assert head and head != "a" * 64
    assert not list(tmp_path.glob("*.json"))


def test_a_receipt_that_cannot_be_built_leaves_the_head_where_it_was(tmp_path):
    head = seal_call(tmp_path, tool="read_file", capability="builtin-read",
                     admission="ALLOWED", args={"fn": object()}, output="",
                     ok=True, outcome="COMPLETED", run_id="r", seq=1,
                     prev="a" * 64)
    assert head == "a" * 64


def test_a_run_that_holds_its_own_bytes_reproduces_its_chain(tmp_path):
    executor = _executor(tmp_path)
    result = executor.execute("read_file", {"path": "hello.txt"})
    held = [json.dumps({"path": "hello.txt"}, sort_keys=True,
                       ensure_ascii=False).encode("utf-8"),
            result.output.encode("utf-8")]
    store = {witness_bytes(b, label="x").sha256: b for b in held}
    assert verify_log(_records(executor), resolve=store.__getitem__)["verdict"] == MATCH
