"""A ledger that fails after the gateway started stops model calls, and resumes cleanly.

Independent review of 2.0.0, finding D2.

The ledger opened at start and a later write failed (a full disk). Every
call still reached the upstream for as long as the failure lasted, and when
writes came back the segment held duplicate sequence numbers. Now the first
failed append marks the ledger failed: later calls answer 503 before any
upstream call, and a resumed ledger verifies and records the gap. Every model
interface writes its end entry after the upstream answered, so a call that is
in flight when the failure comes has already reached the provider; these
tests count it.

Since the fifth review round a call writes a started entry before it contacts
the upstream. A call whose started entry cannot be written is refused with
503 and reaches no provider (tests/test_gateway_write_ahead.py). The tests
here plant the failure after the started entry, on the call's end entry
(`disk.skip = 1`), which is the call in flight. Its end entry is kept and
appended when the ledger resumes, marked `late`.

A real gateway on a loopback port, a stub upstream, the home's on-disk ledger.
The full disk is simulated at the segment's file. No provider is called.
`tests/test_gateway_ledger_live_verify.py` has findings A1 and N2.
"""
import os
import sys
import types

import pytest

from harness import gateway, gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support
from tests.gateway_disk_support import (  # noqa: F401  (fixtures and helpers)
    cleared, gateway_on_disk as _gateway, home, kinds as _kinds, late as _late, rows as _rows,
    rows_call)
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

CALLS = [("/v1/messages", False), ("/v1/messages", True), ("/v1/responses", False),
         ("/v1/messages/count_tokens", False)]
def _body(path, stream):
    return {**BODIES.get(path, MESSAGES), "stream": True} if stream else None


def test_a_failed_append_stops_later_calls_before_the_upstream(keyed, served, monkeypatch, home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(4), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full, disk.skip = True, 1                              # its started entry lands
    status, _headers, body = post(url, "/v1/messages", raw)     # the call in flight
    assert status == 500 and "ledger" in body["error"]["message"]
    assert len(upstream.requests) == 2                          # it had reached the provider
    for path, stream in CALLS:
        for credential in (raw, support.TOKEN):
            status, headers, body = post(url, path, credential, _body(path, stream))
            assert status == 503, (path, stream, body)
            assert "ledger" in body["error"]["message"]
            assert "retry-after" in {name.lower() for name in headers}
    assert gateway._router_ledger() is None                     # what the chat path asks for
    assert len(upstream.requests) == 2, "no call after the failure reached the provider"
    disk.full = False
    assert post(url, "/v1/messages", support.TOKEN)[0] == 200   # writes resumed
    assert len(upstream.requests) == 3
    gateway_ledger.close_all()
    assert _kinds(home) == [
        "endpoint_call_started", "endpoint_call",           # the first call
        "endpoint_call_started",                            # the call in flight: its start
        "ledger_gap",
        "endpoint_call_failed",                             # and its end, appended at the resume
        "endpoint_call_started", "endpoint_call"]           # the call after the resume
    found = gateway_ledger.check(home)
    assert all(segment["ok"] for segment in found), found
    rows = found[0]["rows"]
    gap = rows[3].meta
    assert gap["appends_refused"] == 2 and "No space left" in gap["error"]   # the entry and its failure record
    late, = _late(home)
    assert late.meta["call"] == rows[2].content and late.meta["reason"] == "ledger_failed"
    assert late.meta["charged_tokens"] == 460 and late.meta["delivered"] is False
    assert gateway_ledger_cli.main(["verify"]) == 0             # no call is left unsettled


def test_a_stream_that_meets_the_failure_is_the_last_call_served(keyed, served, monkeypatch,
                                                                 home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    stream = support.stream_answer(stream_bytes("openai", "turn2"))
    url, upstream, ledger, disk = _gateway(monkeypatch, served, [stream, stream, stream], home)
    disk.full, disk.skip = True, 1                              # its started entry lands
    status, _headers, body = post(url, "/v1/messages", raw, {**MESSAGES, "stream": True})
    assert status == 200 and b"delivered_unrecorded_charge" in body     # its text had left
    for credential in (raw, support.TOKEN):
        status, _headers, body = post(url, "/v1/messages", credential,
                                      {**MESSAGES, "stream": True})
        assert status == 503, body
    assert len(upstream.requests) == 1
    disk.full = False
    assert post(url, "/v1/messages", support.TOKEN, {**MESSAGES, "stream": True})[0] == 200
    gateway_ledger.close_all()
    assert _kinds(home) == ["endpoint_call_started", "ledger_gap", "endpoint_call_failed",
                            "endpoint_call_started", "endpoint_call"]
    late, = _late(home)
    assert late.meta["reason"] == "delivered_unrecorded_charge" and late.meta["delivered"] is True
    assert late.meta["key"] == "ci-bot" and len(late.meta["response_sha"]) == 16
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_an_entry_that_reached_the_disk_before_its_commit_failed_is_kept_once(
        keyed, served, monkeypatch, home):
    """The write lands and the commit to the disk fails. The line is in the file."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    real, failing = os.fsync, types.SimpleNamespace(on=False, skip=0)

    def fsync(fd):
        if failing.on and not failing.skip:
            raise OSError(5, "Input/output error")
        failing.skip = max(0, failing.skip - 1)
        return real(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    assert post(url, "/v1/messages", raw)[0] == 200
    failing.on, failing.skip = True, 1          # the started entry commits; the end entry does not
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    failing.on = False
    cleared(url, keys, raw, post)       # suspended by the one rule; the operator clears
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = _rows(home)
    assert [seq for _name, seq, _kind in rows] == list(range(len(rows)))    # no number twice
    kinds = [kind for _name, _seq, kind in rows]
    # The second call's end line is kept. A gap entry written by an attempt to resume
    # whose own commit failed is in the file as well, so there can be two. After the gap
    # comes the late entry that says the reply on that line was held back.
    assert kinds[:4] == ["endpoint_call_started", "endpoint_call",
                         "endpoint_call_started", "endpoint_call"]
    assert kinds[-4:] == ["endpoint_call_failed", "endpoint_call_refused",     # the key's 403
                          "endpoint_call_started", "endpoint_call"]
    assert set(kinds[4:-4]) == {"ledger_gap"}
    late, = _late(home)
    assert late.meta["reason"] == "ledger_failed" and late.meta["call"] == rows_call(home, 2)
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_a_line_cut_short_by_the_failure_is_recorded_as_a_break(keyed, served, monkeypatch,
                                                                 home, capsys):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full, disk.skip = "half", 1            # the started entry lands whole; the end is cut
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    disk.full = False
    cleared(url, keys, raw, post)       # suspended by the one rule; the operator clears
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    found = gateway_ledger.check(home)
    assert [(s["name"], s["ok"]) for s in found] == [("segment-000001.jsonl", False),
                                                     ("segment-000002.jsonl", True)]
    assert "cut short" in found[0]["problem"] and found[0]["entries"] == 3
    assert found[1]["header"]["previous_state"] == "broken"
    assert "a write failed" in found[1]["header"]["reason"]
    # The call in flight started in the broken segment. The new segment's header carries
    # it, and its end entry is there after the gap.
    in_flight = found[0]["rows"][2]
    assert list(found[1]["header"]["open_calls"]) == [in_flight.content]
    assert [entry.kind for entry in found[1]["rows"]] == [
        "ledger_gap", "endpoint_call_failed", "endpoint_call_refused",     # the key's 403
        "endpoint_call_started", "endpoint_call"]
    assert found[1]["rows"][1].meta["call"] == in_flight.content
    assert gateway_ledger_cli.main(["verify"]) == 1             # the gap is a recorded break
    assert "records a break" in capsys.readouterr().out


def test_a_head_record_that_cannot_be_written_stops_later_calls_too(
        keyed, served, monkeypatch, home):
    """The entry is in the segment and the head record after it cannot be rewritten.
    That failure used to leave the ledger in use: every later call reached the provider
    and was then answered 500."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, _disk = _gateway(monkeypatch, served, turn2(3), home)
    real, broken = ledger._write_head, types.SimpleNamespace(on=False, skip=0)

    def write_head():
        if broken.on and not broken.skip:
            raise OSError(5, "Input/output error")
        broken.skip = max(0, broken.skip - 1)
        return real()
    monkeypatch.setattr(ledger, "_write_head", write_head)
    assert post(url, "/v1/messages", raw)[0] == 200
    broken.on, broken.skip = True, 1            # the head after the started entry is written
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    broken.on = False
    cleared(url, keys, raw, post)       # suspended by the one rule; the operator clears
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = _rows(home)
    kinds = [kind for _name, _seq, kind in rows]
    assert [seq for _name, seq, _kind in rows] == list(range(len(rows)))
    assert kinds[:4] == ["endpoint_call_started", "endpoint_call",
                         "endpoint_call_started", "endpoint_call"]
    assert kinds[-4:] == ["endpoint_call_failed", "endpoint_call_refused",     # the key's 403
                          "endpoint_call_started", "endpoint_call"]
    assert set(kinds[4:-4]) == {"ledger_gap"}
    late, = _late(home)
    assert late.meta["reason"] == "ledger_failed" and late.meta["call"] == rows_call(home, 2)
    assert gateway_ledger_cli.main(["verify"]) == 0


@pytest.mark.parametrize("disk_back", [True, False])
def test_a_gateway_that_stops_while_its_ledger_is_failed_records_the_gap_if_it_can(
        keyed, served, monkeypatch, home, disk_back, capsys):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(2), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full, disk.skip = True, 1              # the call in flight: its started entry lands
    assert post(url, "/v1/messages", raw)[0] == 500
    disk.full = not disk_back
    gateway_ledger.close_all()                  # the gateway stops; no call came in between
    disk.full = False
    served_first = ["endpoint_call_started", "endpoint_call", "endpoint_call_started"]
    assert _kinds(home) == served_first + (["ledger_gap", "endpoint_call_failed"] if disk_back
                                           else [])
    assert all(segment["ok"] for segment in gateway_ledger.check(home))
    # With the disk still full the gateway could record nothing more. The call in flight
    # is then a started entry with no end: `verify` names it and exits 3.
    assert gateway_ledger_cli.main(["verify"]) == (0 if disk_back else 3)
    said = capsys.readouterr().out
    assert ("UNSETTLED call" in said) is (not disk_back)
    if not disk_back:
        assert f"UNSETTLED call {gateway_ledger.check(home)[0]['rows'][2].content}" in said


def test_the_gateway_reaches_no_provider_when_the_new_module_cannot_be_imported(
        keyed, served, monkeypatch, home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, _memory = served(turn2(2))
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
    gateway_ledger.close_all()
    import harness
    monkeypatch.delitem(sys.modules, "harness.gateway_ledger")
    monkeypatch.setitem(sys.modules, "harness.gateway_ledger_health", None)
    monkeypatch.delattr(harness, "gateway_ledger_health", raising=False)
    for credential in (raw, support.TOKEN):
        try:
            status = post(url, "/v1/messages", credential)[0]
        except OSError:                                         # the handler failed and closed
            status = 0
        assert status in (0, 500)
    assert upstream.requests == []
