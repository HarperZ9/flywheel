"""The run result carries the chain, so a caller can recheck it without us.

A run that only says what it did is a claim. A run that hands over the witness
records lets whoever reads it recompute every link on their own machine and
decide for themselves, which is the whole reason the chain exists.
"""
from __future__ import annotations

import json

from harness.byte_witness import WITNESS_SCHEMA
from harness.byte_witness_verify import TAMPERED, verify_chain
from harness.local_tools import ToolExecutor, ToolGate
from harness.router_agent import _action_witness


def _executor(tmp_path, *, receipts=False):
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    (root / "hello.txt").write_text("hello world", encoding="utf-8")
    executor = ToolExecutor(
        root=str(root), gate=ToolGate(allow_write=False, allow_exec=False),
        receipt_dir=str(tmp_path / "receipts") if receipts else None)
    executor.init_receipt_chain("test-run")
    return executor


def test_the_chain_is_emitted_without_a_receipt_directory(tmp_path):
    # The receipt directory is an opt-in for files. The chain is what the run
    # did, and a caller who never asked for files is still owed the records.
    executor = _executor(tmp_path, receipts=False)
    executor.execute("read_file", {"path": "hello.txt"})
    block = _action_witness(executor)
    assert block is not None
    assert block["schema"] == WITNESS_SCHEMA
    assert block["count"] == 2                     # one call, both sides
    assert len(block["records"]) == 2


def test_the_emitted_records_still_verify_as_one_chain(tmp_path):
    executor = _executor(tmp_path)
    executor.execute("read_file", {"path": "hello.txt"})
    executor.execute("list_dir", {})
    block = _action_witness(executor)
    result = verify_chain(block["records"])
    assert result["checked"] == 4
    assert result["head"] == block["head_sha256"]


def test_a_rewritten_record_breaks_the_chain_the_caller_was_handed(tmp_path):
    # Without this the block is decoration: it has to be the thing that fails.
    executor = _executor(tmp_path)
    executor.execute("read_file", {"path": "hello.txt"})
    records = _action_witness(executor)["records"]
    records[0]["label"] = "read_file/something-else"
    result = verify_chain(records)
    assert result["verdict"] == TAMPERED


def test_a_run_that_called_no_tool_claims_no_chain(tmp_path):
    # An empty block would read as "checked, nothing found". There is nothing
    # to check, so the key is absent and the caller is not invited to conclude.
    assert _action_witness(_executor(tmp_path)) is None


def test_the_block_says_what_it_does_not_prove(tmp_path):
    executor = _executor(tmp_path)
    executor.execute("list_dir", {})
    assert _action_witness(executor)["does_not_prove"]


def test_the_block_is_the_shape_the_desktop_surface_parses(tmp_path):
    # desktop/lib/models/byte_witness_chain.dart reads a run result by looking
    # for action_witness.records. If this nests differently, that panel shows
    # a parse failure for a run that is perfectly intact.
    executor = _executor(tmp_path)
    executor.execute("list_dir", {})
    out = json.loads(json.dumps({"action_witness": _action_witness(executor)}))
    assert isinstance(out["action_witness"]["records"], list)


def test_an_executor_without_the_accessor_is_not_an_error(tmp_path):
    # Callers pass their own executors. A missing chain is a missing chain.
    assert _action_witness(object()) is None
