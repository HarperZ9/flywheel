"""The record a debug session leaves, and what it takes to break it.

A debug session is the highest-value thing an agent does that nobody can check
afterwards. It reads a live process: a breakpoint hit, a variable, an expression
evaluated against real memory. Those readings become claims in the answer, and
the wire they came off is gone the moment the adapter exits.

So the tests here are about what survives. The frames in order, the refusals
beside the allows, the stops in the order they happened, and a fold that carries
counts rather than the values themselves. The last one has a control: a variable
read during the session must not be findable anywhere in the summary, because a
receipt that quietly copies the debuggee's memory is a leak wearing the clothes
of an audit trail.
"""
import json
import sys
import time
from pathlib import Path

import pytest

from harness.action_witness import (RESERVED_CONTEXT, open_log, read_log,
                                    verify_log)
from harness.byte_witness_verify import (BYTES_UNAVAILABLE, DIGEST_MISMATCH,
                                         LINK_BROKEN, MATCH, TAMPERED,
                                         UNVERIFIABLE)
from harness.dap_client import DapClient
from harness.dap_policy import DenyAll
from harness.dap_witness import (DECISION_ACTION, FRAME_ACTION, SESSION_ACTION,
                                 STOP_ACTION, DapWitness, does_not_prove,
                                 stop_summary, summarize, transcript_resolver)

FAKE = [sys.executable, str(Path(__file__).parent / "fake_dap_adapter.py")]


def wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"nothing satisfied {predicate} within {timeout:g}s")


@pytest.fixture
def session(tmp_path):
    """One recorded session: three breakpoints, a stop, and a variable read."""
    clients = []

    def run(*flags, transcript=None, policy=None):
        log = open_log("dap-run-1", directory=tmp_path)
        witness = DapWitness(log, transcript=transcript)
        policy = policy if policy is not None else DenyAll()
        client = DapClient.start(FAKE + list(flags), root=tmp_path,
                                 policy=policy,
                                 observer=witness.observe_frame)
        clients.append(client)
        client.start_session("fake", launch={"program": "program.py"},
                             breakpoints={"program.py": [10, 999, 30]},
                             timeout=20.0)
        client.wait_for_stop(timeout=20.0)
        return witness, log, client, policy

    yield run
    for client in clients:
        client.disconnect(timeout=5.0)
        client.close()


def test_every_frame_in_both_directions_becomes_a_link(session):
    witness, log, client, _ = session()
    frames = [r for r in read_log(log.path)
              if r["context"]["action"] == FRAME_ACTION]
    assert witness.frames == len(frames)
    # A session that came up at all crossed initialize and its answer, launch,
    # the two breakpoint requests and their answers, and the stop.
    assert witness.frames >= 8
    assert {f["context"]["direction"] for f in frames} == {"sent", "received"}


def test_a_response_is_tied_to_its_request_on_the_record(session):
    # The DAP-specific part of the context. A record that carried `id` the way
    # the shared witness does would show blanks here, and a reader could not
    # tell which answer belonged to which request.
    _, log, _, _ = session()
    frames = [r["context"] for r in read_log(log.path)
              if r["context"]["action"] == FRAME_ACTION]
    launches = [f for f in frames if f["command"] == "launch"]
    sent = [f for f in launches if f["direction"] == "sent"][0]
    answer = [f for f in launches if f["direction"] == "received"][0]
    assert answer["request_seq"] == sent["message_seq"]
    assert answer["outcome"] == "result"
    assert sent["outcome"] == ""
    # A request was not an answer to anything, and a record that said otherwise
    # would invite a reader to tie it to whatever the empty value resembled.
    assert "request_seq" not in sent


def test_the_frames_own_numbers_are_not_the_chains_numbers(session):
    # The bug this pins: `seq` belongs to the chain, and a context key of that
    # name is dropped rather than written. A witness that stored the adapter's
    # number there produced a record that read plausibly, matched `request_seq`
    # whenever the two counters happened to line up, and was the log's position
    # every time.
    _, log, _, _ = session()
    frames = [r["context"] for r in read_log(log.path)
              if r["context"]["action"] == FRAME_ACTION]
    assert not RESERVED_CONTEXT.intersection(
        {"direction", "type", "command", "message_seq", "request_seq",
         "outcome"})
    # Each side numbers its own messages from one, so both counters restart and
    # neither can be the chain's single run of positions.
    assert [f["seq"] for f in frames] == list(range(len(frames)))
    sent = [f["message_seq"] for f in frames if f["direction"] == "sent"]
    assert sent == sorted(sent)
    assert min(sent) == 1


def test_the_fold_carries_the_counts_the_wire_reported(session):
    witness, log, client, _ = session()
    recorded = witness.record_session(client.session, adapter="fake")
    assert recorded["breakpoints_requested"] == 3
    assert recorded["breakpoints_verified"] == 2
    assert recorded["sources_with_breakpoints"] == 1
    assert "supportsConfigurationDoneRequest" in recorded["capabilities"]
    # False is not a capability. A list of every name the adapter mentioned
    # would read as support for things it said it does not do.
    assert "supportsConditionalBreakpoints" not in recorded["capabilities"]
    assert "initialized" in recorded["event_names"]
    assert [r["context"]["action"] for r in read_log(log.path)].count(
        SESSION_ACTION) == 1
    assert recorded["sha256"] in {r["sha256"] for r in read_log(log.path)}


def test_a_value_read_out_of_the_debuggee_is_not_copied_into_the_summary(
        session):
    # The control on the whole design. The frame chain already binds the frames
    # that carried these values, and a variable's value is the part of a debug
    # session most likely to be a secret. A receipt is not a second transcript.
    witness, _, client, _ = session()
    read = client.frame_variables(1)
    assert [entry["value"] for entry in read["Locals"]] == ["42", "list(3)"]
    evaluated = client.evaluate("total", frame_id=1)
    assert evaluated["result"] == "total in watch"
    # Over the payload rather than the record, because the record carries a
    # digest and a hex string contains every pair of digits eventually.
    text = json.dumps(summarize(client.session, adapter="fake"))
    for value in ('"42"', "list(3)", "total in watch", "expensive_was_read"):
        assert value not in text
    witness.record_session(client.session, adapter="fake")


def test_a_refused_terminal_is_on_the_record_with_what_it_asked_for(session):
    # The refusal is the part a reader cannot reconstruct from the outcome. A
    # run where the adapter asked to start a process and was told no looks,
    # from its exit code alone, exactly like a run where it never asked.
    witness, log, _, policy = session("--ask-terminal")
    wait_for(lambda: policy.decisions)
    assert witness.record_decisions(policy) == 1
    written = [r for r in read_log(log.path)
               if r["context"]["action"] == DECISION_ACTION]
    assert written[0]["context"]["allowed"] is False
    assert written[0]["context"]["policy"] == "deny-all"
    # Recording twice does not write the same decision twice.
    assert witness.record_decisions(policy) == 0


def test_stops_are_recorded_in_the_order_they_happened(session):
    # Taken at each stop rather than folded once at the end. A session summed
    # up afterwards could be rewritten to say the breakpoints were hit in a
    # different order and nothing in the chain would break.
    witness, log, client, _ = session()
    first = witness.record_stop(client.session.stop)
    client.step(1, over=True)
    second = witness.record_stop(wait_for(lambda: client.session.stop))
    assert [first["reason"], second["reason"]] == ["breakpoint", "step"]
    assert first["hit_breakpoint_ids"] == [1]
    stops = [r for r in read_log(log.path)
             if r["context"]["action"] == STOP_ACTION]
    assert [s["context"]["reason"] for s in stops] == ["breakpoint", "step"]


def test_the_chain_and_its_transcript_verify_offline_together(session,
                                                              tmp_path):
    transcript = tmp_path / "frames.jsonl"
    witness, log, client, _ = session(transcript=transcript)
    witness.record_session(client.session, adapter="fake")
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == MATCH
    assert result["broken_at"] is None
    assert result["checked"] == len(read_log(log.path))


def test_a_chain_without_its_bytes_is_unverifiable_and_says_so(session):
    _, log, _, _ = session()
    result = verify_log(log.path)
    assert result["verdict"] == UNVERIFIABLE
    assert result["failure_class"] == BYTES_UNAVAILABLE


def test_an_edited_frame_breaks_the_chain_from_that_point(session):
    _, log, _, _ = session()
    records = read_log(log.path)
    records[3]["sha256"] = "0" * 64
    result = verify_log(records)
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == LINK_BROKEN
    assert result["broken_at"] == 4


def test_a_changed_thread_in_the_transcript_is_caught(session, tmp_path):
    transcript = tmp_path / "frames.jsonl"
    witness, log, client, _ = session(transcript=transcript)
    witness.record_stop(client.session.stop)
    entries = [json.loads(line) for line in
               transcript.read_text(encoding="utf-8").splitlines()]
    changed = 0
    for entry in entries:
        if entry["payload"].get("thread_id") == 1:
            entry["payload"]["thread_id"] = 2    # same length, so digest is it
            changed += 1
    assert changed >= 1
    transcript.write_text(
        "".join(json.dumps(entry) + chr(10) for entry in entries),
        encoding="utf-8")
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == DIGEST_MISMATCH


def test_a_session_that_never_started_folds_without_inventing_numbers():
    # A fold that reported zero breakpoints and a clean exit for a session that
    # never connected would read as a run that found nothing, which is a
    # different claim from a run that never happened.
    class Never:
        capabilities = None
        breakpoints = {}
        terminated = False

        class events:
            seen = []
            output = []
            exit_code = None

        def verified_breakpoints(self):
            return (0, 0)

    summary = summarize(Never(), adapter="")
    assert summary["capabilities"] == []
    assert summary["exit_code"] is None
    assert summary["terminated"] is False
    assert summary["does_not_prove"]


def test_a_stop_with_nothing_attached_still_names_its_reason():
    class Bare:
        reason = "pause"
        thread_id = None
        description = ""
        text = ""
        all_threads = False
        hit_breakpoint_ids = ()

    summary = stop_summary(Bare())
    assert summary["reason"] == "pause"
    assert summary["hit_breakpoint_ids"] == []


def test_what_the_record_does_not_prove_names_the_debuggee_limit():
    lines = does_not_prove()
    assert lines
    assert any("independent observation" in line for line in lines)
    assert any("not evidence that the line was reached" in line
               for line in lines)
