"""The run result carries the chain, so a caller can recheck it without us.

A run that only says what it did is a claim. A run that hands over the witness
records lets whoever reads it recompute every link on their own machine and
decide for themselves, which is the whole reason the chain exists.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.byte_witness import WITNESS_SCHEMA
from harness.byte_witness_verify import TAMPERED, verify_chain
from harness.local_tools import ToolExecutor, ToolGate
from harness import router_agent
from harness.router_agent import _action_witness


DESKTOP_MODELS = (Path(__file__).resolve().parent.parent / "desktop" / "lib"
                  / "models")
# The parser on the other side of the wire, and the names it looks for.
DART_PARSER = DESKTOP_MODELS / "byte_witness_chain.dart"
DART_SCHEMA = DESKTOP_MODELS / "byte_witness.dart"
READ_BY_THE_PANEL = ("action_witness", "schema", "records", "records_omitted")


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


def test_a_chain_over_budget_is_omitted_whole_and_says_so(tmp_path,
                                                          monkeypatch):
    # A shortened list would verify as TAMPERED and accuse the run of what the
    # budget did. The count and the head still describe the chain.
    monkeypatch.setattr(router_agent, "WITNESS_RECORD_BUDGET", 100)
    executor = _executor(tmp_path)
    executor.execute("list_dir", {})
    block = _action_witness(executor)
    assert "records" not in block
    assert block["count"] == 2
    assert len(block["head_sha256"]) == 64
    assert "action-witness.jsonl" in block["records_omitted"]


@pytest.mark.skipif(not DART_PARSER.exists(),
                    reason="the Flutter surface is not checked out")
def test_the_panel_reads_names_this_block_still_writes(tmp_path, monkeypatch):
    # Rename one of these here and a perfectly intact run reads as unparseable
    # on the surface, with nothing failing in between to say so.
    executor = _executor(tmp_path)
    executor.execute("list_dir", {})
    written = set(_action_witness(executor)) | {"action_witness"}
    monkeypatch.setattr(router_agent, "WITNESS_RECORD_BUDGET", 100)
    written |= set(_action_witness(executor))
    assert set(READ_BY_THE_PANEL) <= written
    parser = DART_PARSER.read_text(encoding="utf-8")
    missing = [n for n in READ_BY_THE_PANEL if f"'{n}'" not in parser]
    assert not missing, f"the Dart parser does not read: {', '.join(missing)}"
    assert WITNESS_SCHEMA in DART_SCHEMA.read_text(encoding="utf-8")
