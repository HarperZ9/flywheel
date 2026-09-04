"""Tests for the action layer: one chain per run, and a hole that shows."""
from __future__ import annotations

import hashlib
import json

import pytest

from harness.action_witness import (ACTION_SCHEMA, CANONICAL_JSON, INPUT, LOG_NAME,
                                    OUTPUT, UTF8, does_not_prove, observe,
                                    observe_action, open_log, read_log, verify_log)
from harness.byte_witness import WitnessError, witness_bytes
from harness.byte_witness_verify import BYTES_UNAVAILABLE, LINK_BROKEN, MALFORMED
from harness.evidence_json import canonical_bytes
from harness.tool_call_receipt import MATCH, TAMPERED, UNVERIFIABLE

ARGS = {"path": "harness/loop.py"}
RESULT = "the file the tool read back"


def _store(*payloads):
    return {witness_bytes(p, label="x").sha256: p for p in payloads}


def test_one_action_leaves_its_input_and_its_output_in_that_order(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    summary = observe_action(log, action="tool:read_file", seq=1,
                             args=ARGS, output=RESULT)
    kinds = [record["context"]["kind"] for record in log.records()]
    assert kinds == [INPUT, OUTPUT]
    assert summary["link"] == log.head()
    assert summary["input"]["sha256"] == hashlib.sha256(canonical_bytes(ARGS)).hexdigest()
    assert summary["output"]["sha256"] == hashlib.sha256(RESULT.encode(UTF8)).hexdigest()


def test_the_log_carries_the_digests_and_never_the_bytes(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    observe_action(log, action="tool:run", seq=1,
                   args={"cmd": "echo the-secret-argument"},
                   output="the-secret-output")
    raw = (tmp_path / LOG_NAME).read_bytes()
    assert b"the-secret-argument" not in raw
    assert b"the-secret-output" not in raw
    assert raw.count(b"\n") == 2


def test_the_run_reproduces_when_someone_holds_the_bytes(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    observe_action(log, action="tool:read_file", seq=1, args=ARGS, output=RESULT)
    observe_action(log, action="tool:write_file", seq=2, args=ARGS, output="")
    store = _store(canonical_bytes(ARGS), RESULT.encode(UTF8), b"")
    result = verify_log(tmp_path / LOG_NAME, resolve=store.__getitem__)
    assert result["verdict"] == MATCH
    assert result["checked"] == 4


def test_the_record_says_how_the_bytes_were_produced(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    summary = observe_action(log, action="tool:run", seq=1,
                             args={"cmd": "ls"}, output=b"\x00\x01raw")
    assert summary["input"]["encoding"] == CANONICAL_JSON
    assert summary["output"]["encoding"] == "none"
    assert [record["context"]["encoding"] for record in log.records()] == [
        CANONICAL_JSON, "none"]


def test_a_dropped_write_leaves_a_broken_log_and_not_an_intact_one(tmp_path):
    # The one failure this layer cannot afford is a hole that still reads as a
    # clean run, so the middle record is written into a path that refuses it and
    # the chain is checked afterwards.
    log = open_log("run-1", directory=tmp_path)
    observe(log, b"first", action="tool:run", kind=INPUT, seq=1)
    good, log.path = log.path, tmp_path
    observe(log, b"second", action="tool:run", kind=OUTPUT, seq=1)
    log.path = good
    observe(log, b"third", action="tool:run", kind=INPUT, seq=2)
    assert log.dropped == 1
    assert len(read_log(tmp_path / LOG_NAME)) == 2
    result = verify_log(tmp_path / LOG_NAME)
    assert (result["verdict"], result["failure_class"]) == (TAMPERED, LINK_BROKEN)
    assert result["broken_at"] == 1


def test_a_caller_cannot_overwrite_the_action_facts(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    witness = observe(log, b"x", action="tool:run", kind=INPUT, seq=4,
                      context={"action": "something-else", "run_id": "run-9",
                               "note": "kept"})
    context = witness.record()["context"]
    assert context["action"] == "tool:run"
    assert context["run_id"] == "run-1"
    assert context["seq"] == 4
    assert context["note"] == "kept"


def test_an_exotic_context_value_becomes_text_rather_than_a_refusal(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    witness = observe(log, b"x", action="tool:run", kind=INPUT, seq=1,
                      context={"path": tmp_path, "ok": True, "tries": 3})
    context = witness.record()["context"]
    assert context["path"] == str(tmp_path)
    assert context["ok"] is True and context["tries"] == 3


def test_an_action_inserted_afterwards_breaks_every_link_after_it(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    observe_action(log, action="tool:read_file", seq=1, args=ARGS, output=RESULT)
    observe_action(log, action="tool:run", seq=2, args={"cmd": "ls"}, output="ok")
    chain = read_log(tmp_path / LOG_NAME)
    forged = json.loads(json.dumps(chain[1]))
    forged["label"] = "tool:read_file/output (edited)"
    assert verify_log([chain[0], forged] + chain[2:])["verdict"] == TAMPERED


def test_a_corrupted_line_is_unverifiable_and_not_a_shorter_clean_chain(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    observe_action(log, action="tool:run", seq=1, args={"cmd": "ls"}, output="ok")
    with (tmp_path / LOG_NAME).open("ab") as stream:
        stream.write(b"{not json at all\n")
    result = verify_log(tmp_path / LOG_NAME)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)
    assert result["broken_at"] == 2


def test_the_same_bytes_witnessed_twice_in_one_run_do_not_repeat_a_link(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    first = observe(log, b"identical", action="tool:run", kind=OUTPUT, seq=1)
    second = observe(log, b"identical", action="tool:run", kind=OUTPUT, seq=2)
    assert first.sha256 == second.sha256
    assert first.link() != second.link()


def test_a_log_with_no_directory_still_chains(tmp_path):
    log = open_log("run-1")
    observe_action(log, action="tool:run", seq=1, args={"cmd": "ls"}, output="ok")
    assert log.path is None and len(log) == 2
    store = _store(canonical_bytes({"cmd": "ls"}), b"ok")
    assert verify_log(log.records(), resolve=store.__getitem__)["verdict"] == MATCH


def test_a_run_needs_a_name(tmp_path):
    for bad in ["", None, 7]:
        with pytest.raises(WitnessError):
            open_log(bad, directory=tmp_path)


def test_a_log_that_is_not_there_is_a_verdict_and_not_a_raise(tmp_path):
    result = verify_log(tmp_path / "no-such-run.jsonl")
    assert result["verdict"] == UNVERIFIABLE
    assert "could not be read" in result["detail"]


def test_an_empty_log_is_unverifiable_rather_than_a_clean_run(tmp_path):
    (tmp_path / LOG_NAME).write_bytes(b"")
    result = verify_log(tmp_path / LOG_NAME)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, MALFORMED)


def test_a_summary_names_the_schema_and_the_action(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    summary = observe_action(log, action="tool:read_file", seq=3,
                             args=ARGS, output=RESULT)
    assert summary["schema"] == ACTION_SCHEMA
    assert (summary["action"], summary["seq"]) == ("tool:read_file", 3)
    assert summary["input"]["bytes"] == len(canonical_bytes(ARGS))


def test_without_a_resolver_a_log_is_linked_and_not_reproduced(tmp_path):
    log = open_log("run-1", directory=tmp_path)
    observe_action(log, action="tool:run", seq=1, args={"cmd": "ls"}, output="ok")
    result = verify_log(tmp_path / LOG_NAME)
    assert (result["verdict"], result["failure_class"]) == (UNVERIFIABLE, BYTES_UNAVAILABLE)


def test_the_action_layer_says_what_it_leaves_open():
    lines = does_not_prove()
    assert len(lines) > 5
    assert any("taken around it" in line for line in lines)
    assert any("caller's word" in line for line in lines)
