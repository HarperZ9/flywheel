"""The record a language server session leaves, and what it takes to break it.

The LSP-specific part of the record is the version and the encoding an answer
was taken under. A range is a pair of numbers, and numbers without those two
facts describe a span in some file at some revision under some counting rule,
which is not a record. So the tests here check that the pair survives the fold,
and that changing either one in the transcript is caught.
"""
import json
import sys
import time
from pathlib import Path

import pytest

from harness.action_witness import open_log, read_log, verify_log
from harness.byte_witness_verify import (BYTES_UNAVAILABLE, DIGEST_MISMATCH,
                                         LINK_BROKEN, MATCH, TAMPERED,
                                         UNVERIFIABLE)
from harness.lsp_client import LspClient
from harness.lsp_incoming import Published
from harness.lsp_positions import UTF8, UTF16
from harness.lsp_witness import (ANSWER_ACTION, FRAME_ACTION, LspWitness,
                                 PUBLISHED_ACTION, count_of, does_not_prove,
                                 published_summary, summarize,
                                 transcript_resolver)

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"nothing satisfied {predicate} within {timeout:g}s")


@pytest.fixture
def session(tmp_path):
    """One recorded session: open a file, take its diagnostics, ask once."""
    clients = []

    def run(transcript=None, encoding=UTF16):
        log = open_log("lsp-run-1", directory=tmp_path)
        witness = LspWitness(log, transcript=transcript)
        client = LspClient.start(FAKE + ["--encoding", encoding],
                                 root=tmp_path,
                                 observer=witness.observe_frame)
        clients.append(client)
        client.initialize()
        path = tmp_path / "a.py"
        path.write_text("broken thing\nsecond\n", encoding="utf-8")
        uri = client.open(path, "python")
        wait_for(lambda: client.diagnostics(uri).items)
        answer = client.ask("definition", uri, line=0, character=0)
        return witness, log, client, uri, answer

    yield run
    for client in clients:
        client.close()


def test_every_frame_in_both_directions_becomes_a_link(session):
    witness, log, _, _, answer = session()
    # initialize and its answer, initialized, didOpen, publishDiagnostics,
    # the definition request and its answer: seven, in both directions.
    assert witness.frames == 7
    summary = witness.record_answer(answer)
    actions = [r["context"]["action"] for r in read_log(log.path)]
    assert actions.count(FRAME_ACTION) == 7
    assert actions.count(ANSWER_ACTION) == 1
    assert summary["sha256"] in {r["sha256"] for r in read_log(log.path)}


def test_the_answer_on_the_record_carries_the_version_and_the_encoding(
        session):
    _, _, client, uri, answer = session()
    summary = summarize(answer)
    assert summary["uri"] == uri
    assert summary["version"] == 1
    assert summary["encoding"] == UTF16
    assert summary["current"] is True
    assert summary["lines"] == 3
    assert summary["results"] == 1


def test_an_answer_taken_before_an_edit_records_that_it_is_no_longer_current(
        session):
    _, _, client, uri, answer = session()
    client.replace(uri, "different\n")
    # The answer object froze `current` when it landed, so the fold reports the
    # run as it happened. Re-asking is how a caller gets a fresh answer; the
    # record is not the place to quietly update one.
    stale = client.ask("definition", uri, line=0, character=0)
    client.replace(uri, "again\n")
    assert summarize(answer)["current"] is True
    assert summarize(stale)["version"] == 2
    assert client.documents.get(uri).version == 3


def test_the_encoding_the_server_chose_is_the_one_on_the_record(session):
    _, _, _, _, answer = session(encoding=UTF8)
    # The false-success control for the record. Two runs producing the same
    # character numbers under different encodings describe different spans, and
    # only this field tells them apart.
    assert summarize(answer)["encoding"] == UTF8


def test_the_chain_and_its_transcript_verify_offline_together(session,
                                                              tmp_path):
    transcript = tmp_path / "frames.jsonl"
    witness, log, _, _, answer = session(transcript=transcript)
    witness.record_answer(answer)
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == MATCH
    assert result["broken_at"] is None
    assert result["checked"] == len(read_log(log.path))


def test_a_chain_without_its_bytes_is_unverifiable_and_says_so(session):
    _, log, _, _, _ = session()
    result = verify_log(log.path)
    assert result["verdict"] == UNVERIFIABLE
    assert result["failure_class"] == BYTES_UNAVAILABLE


def test_an_edited_frame_breaks_the_chain_from_that_point(session):
    _, log, _, _, _ = session()
    records = read_log(log.path)
    records[3]["sha256"] = "0" * 64
    result = verify_log(records)
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == LINK_BROKEN
    assert result["broken_at"] == 4


def test_a_changed_version_in_the_record_is_caught(session, tmp_path):
    transcript = tmp_path / "frames.jsonl"
    witness, log, _, _, answer = session(transcript=transcript)
    witness.record_answer(answer)
    entries = [json.loads(line) for line in
               transcript.read_text(encoding="utf-8").splitlines()]
    changed = 0
    for entry in entries:
        if entry["payload"].get("version") == 1:
            entry["payload"]["version"] = 2      # same length, so digest is it
            changed += 1
    assert changed == 1
    transcript.write_text(
        "".join(json.dumps(entry) + chr(10) for entry in entries),
        encoding="utf-8")
    result = verify_log(log.path, resolve=transcript_resolver(transcript))
    assert result["verdict"] == TAMPERED
    assert result["failure_class"] == DIGEST_MISMATCH


def test_the_direction_and_the_method_are_on_the_record(session):
    _, log, _, _, _ = session()
    frames = [r for r in read_log(log.path)
              if r["context"]["action"] == FRAME_ACTION]
    methods = [f["context"]["method"] for f in frames]
    assert "initialize" in methods
    assert "textDocument/publishDiagnostics" in methods
    assert {f["context"]["direction"] for f in frames} == {"sent", "received"}


def test_a_published_set_is_counted_and_not_repeated(session, tmp_path):
    witness, log, client, uri, _ = session()
    recorded = witness.record_published(client.diagnostics(uri))
    assert recorded["diagnostics"] == 1
    assert recorded["version"] == 1
    assert recorded["current"] is True
    assert recorded["severities"] == [1]
    # The messages are bound by the frame that carried them and are deliberately
    # not copied here. A receipt is not a second transcript.
    assert "broken symbol" not in json.dumps(recorded)
    assert [r["context"]["action"] for r in read_log(log.path)].count(
        PUBLISHED_ACTION) == 1


def test_a_set_nobody_published_is_recorded_as_unknown_not_clean():
    summary = published_summary(Published(uri="file:///w/never.py"))
    assert summary["diagnostics"] == 0
    assert summary["version"] is None
    assert summary["current"] is None
    assert summary["severities"] == []


def test_the_count_separates_nothing_to_say_from_one_answer():
    assert count_of(None) == 0
    assert count_of([]) == 0
    assert count_of({}) == 0
    assert count_of([{"uri": "a"}, {"uri": "b"}]) == 2
    assert count_of({"contents": "text"}) == 1


def test_what_the_record_does_not_prove_names_the_encoding_limit():
    lines = does_not_prove()
    assert lines
    assert any("negotiated encoding" in line for line in lines)
    assert any("not that the server's answer is right" in line
               for line in lines)
