"""A ledger that fails after the gateway started stops model calls, and resumes cleanly.

Independent review of 2.0.0, finding D2.

The ledger opened at start and a later write failed (a full disk). Every
call still reached the upstream for as long as the failure lasted, and when
writes came back the segment held duplicate sequence numbers. Now the first
failed append marks the ledger failed: later calls answer 503 before any
upstream call, and a resumed ledger verifies and records the gap. Every model
interface writes its entry after the upstream answered, so the one call that
meets the failure has already reached the provider; these tests count it.

A real gateway on a loopback port, a stub upstream, the home's on-disk ledger.
The full disk is simulated at the segment's file. No provider is called.
`tests/test_gateway_ledger_live_verify.py` has findings A1 and N2.
"""
import io
import os
import sys
import types

import pytest

from harness import gateway, gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

CALLS = [("/v1/messages", False), ("/v1/messages", True), ("/v1/responses", False),
         ("/v1/messages/count_tokens", False)]
ENOSPC = (28, "No space left on device")


@pytest.fixture
def home(monkeypatch, tmp_path):
    where = tmp_path / "home"
    where.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(where))
    yield where
    gateway_ledger.close_all()


class _Disk(io.RawIOBase):
    """The segment's file with a switch: `full` refuses writes, `half` takes half a line."""

    def __init__(self, real, state):
        self.real, self.state = real, state

    def writable(self):
        return True

    def write(self, data):
        if self.state.full == "half":
            self.state.full = True
            self.real.write(bytes(data)[:len(data) // 2])
            raise OSError(*ENOSPC)
        if self.state.full:
            raise OSError(*ENOSPC)
        return self.real.write(bytes(data))

    def fileno(self):
        return self.real.fileno()


def _gateway(monkeypatch, served, answers, home):
    """(url, upstream, ledger, disk): a gateway on the home's ledger, and the disk switch."""
    url, upstream, _memory = served(answers)
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
    ledger = gateway._router_ledger()
    disk = types.SimpleNamespace(full=False)
    ledger._file = _Disk(ledger._file, disk)
    health = sys.modules.get("harness.gateway_ledger_health")
    if health is not None:              # a reopened segment is on the same full disk
        real = health._put

        def put(file, data):
            if disk.full and not isinstance(file, _Disk):
                raise OSError(*ENOSPC)
            return real(file, data)
        monkeypatch.setattr(health, "_put", put)
        monkeypatch.setattr(health, "RETRY_SECONDS", 0.0)   # try to resume on every call
    return url, upstream, ledger, disk


def _rows(home) -> list:
    return [(segment["name"], entry.seq, entry.kind)
            for segment in gateway_ledger.check(home) for entry in segment["rows"]]


def _body(path, stream):
    return {**BODIES.get(path, MESSAGES), "stream": True} if stream else None


def test_a_failed_append_stops_later_calls_before_the_upstream(keyed, served, monkeypatch, home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(4), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full = True
    status, _headers, body = post(url, "/v1/messages", raw)     # the call that meets the failure
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
    assert _rows(home) == [("segment-000001.jsonl", 0, "endpoint_call"),
                           ("segment-000001.jsonl", 1, "ledger_gap"),
                           ("segment-000001.jsonl", 2, "endpoint_call")]
    found = gateway_ledger.check(home)
    assert all(segment["ok"] for segment in found), found
    gap = found[0]["rows"][1].meta
    assert gap["appends_refused"] == 2 and "No space left" in gap["error"]   # the entry and its failure record
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_a_stream_that_meets_the_failure_is_the_last_call_served(keyed, served, monkeypatch,
                                                                 home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    stream = support.stream_answer(stream_bytes("openai", "turn2"))
    url, upstream, ledger, disk = _gateway(monkeypatch, served, [stream, stream, stream], home)
    disk.full = True
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
    assert [kind for _name, _seq, kind in _rows(home)] == ["ledger_gap", "endpoint_call"]
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_an_entry_that_reached_the_disk_before_its_commit_failed_is_kept_once(
        keyed, served, monkeypatch, home):
    """The write lands and the commit to the disk fails. The line is in the file."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    real, failing = os.fsync, types.SimpleNamespace(on=False)

    def fsync(fd):
        if failing.on:
            raise OSError(5, "Input/output error")
        return real(fd)
    monkeypatch.setattr(os, "fsync", fsync)
    assert post(url, "/v1/messages", raw)[0] == 200
    failing.on = True
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    failing.on = False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = _rows(home)
    assert [seq for _name, seq, _kind in rows] == list(range(len(rows)))    # no number twice
    kinds = [kind for _name, _seq, kind in rows]
    # The second call's line is kept. A gap entry written by an attempt to resume
    # whose own commit failed is in the file as well, so there can be two.
    assert kinds[:2] == ["endpoint_call", "endpoint_call"] and kinds[-1] == "endpoint_call"
    assert set(kinds[2:-1]) == {"ledger_gap"}
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_a_line_cut_short_by_the_failure_is_recorded_as_a_break(keyed, served, monkeypatch,
                                                                 home, capsys):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full = "half"
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    disk.full = False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    found = gateway_ledger.check(home)
    assert [(s["name"], s["ok"]) for s in found] == [("segment-000001.jsonl", False),
                                                     ("segment-000002.jsonl", True)]
    assert "cut short" in found[0]["problem"] and found[0]["entries"] == 1
    assert found[1]["header"]["previous_state"] == "broken"
    assert "a write failed" in found[1]["header"]["reason"]
    assert [entry.kind for entry in found[1]["rows"]] == ["ledger_gap", "endpoint_call"]
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
    real, broken = ledger._write_head, types.SimpleNamespace(on=False)

    def write_head():
        if broken.on:
            raise OSError(5, "Input/output error")
        return real()
    monkeypatch.setattr(ledger, "_write_head", write_head)
    assert post(url, "/v1/messages", raw)[0] == 200
    broken.on = True
    assert post(url, "/v1/messages", raw)[0] == 500
    assert post(url, "/v1/messages", raw)[0] == 503 and len(upstream.requests) == 2
    broken.on = False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = _rows(home)
    kinds = [kind for _name, _seq, kind in rows]
    assert [seq for _name, seq, _kind in rows] == list(range(len(rows)))
    assert kinds[:2] == ["endpoint_call", "endpoint_call"] and kinds[-1] == "endpoint_call"
    assert set(kinds[2:-1]) == {"ledger_gap"}
    assert gateway_ledger_cli.main(["verify"]) == 0


@pytest.mark.parametrize("disk_back", [True, False])
def test_a_gateway_that_stops_while_its_ledger_is_failed_records_the_gap_if_it_can(
        keyed, served, monkeypatch, home, disk_back):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(2), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full = True
    assert post(url, "/v1/messages", raw)[0] == 500
    disk.full = not disk_back
    gateway_ledger.close_all()                  # the gateway stops; no call came in between
    disk.full = False
    kinds = [kind for _name, _seq, kind in _rows(home)]
    assert kinds == (["endpoint_call", "ledger_gap"] if disk_back else ["endpoint_call"])
    assert all(segment["ok"] for segment in gateway_ledger.check(home))


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
