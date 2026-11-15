"""The gateway ledger under write failures: findings R5 and R6 of the third review.

R5   a write that fails with an error other than OSError or ValueError did not
     mark the ledger failed: every later call reached the provider and was
     answered 500 with no entry. Any failure of the write now marks it.
R6   when the head record cannot be rewritten, the entry is already in the
     segment as `endpoint_call` while the reply is held back and the client
     is told 500. The `ledger_gap` entry of the resumed ledger now names that
     entry, so the record says which served-looking entry was not served.

A real gateway on a loopback port, a stub upstream, the home's on-disk ledger.
The failures are planted at the segment's file and at the head record. No
provider is called.
"""
import types

import pytest

from harness import gateway_ledger, gateway_ledger_cli
from tests.gateway_keys_support import keyed, post, served, turn2  # noqa: F401  (fixtures)
from tests.test_gateway_ledger_write_failure import (  # noqa: F401  (fixtures and helpers)
    _Disk, _gateway, home)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


class _Odd(_Disk):
    """A segment file whose write fails with an error that is not an OSError."""

    def write(self, data):
        if self.state.odd is not None:
            raise self.state.odd("planted by the test")
        return super().write(data)


@pytest.mark.parametrize("error", [RuntimeError, MemoryError])
def test_r5_a_write_that_fails_with_any_error_stops_later_calls_before_the_upstream(
        keyed, served, monkeypatch, home, error):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(6), home)
    disk.odd = None
    ledger._file = _Odd(ledger._file.real, disk)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.odd, disk.full = error, True       # the write fails; a reopened file is refused too
    status, _headers, body = post(url, "/v1/messages", raw)
    assert status == 500 and "ledger" in body["error"]["message"]
    assert ledger.failed is not None and error.__name__ in ledger.failed["error"]
    statuses = [post(url, "/v1/messages", raw)[0] for _ in range(3)]
    assert statuses == [503, 503, 503]
    assert len(upstream.requests) == 2, "only the call that met the failure reached the provider"
    disk.odd, disk.full = None, False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = [entry for segment in gateway_ledger.check(home) for entry in segment["rows"]]
    assert [entry.kind for entry in rows].count("ledger_gap") == 1
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_r5_a_resume_that_fails_with_any_error_leaves_the_ledger_failed_and_answers_503(
        keyed, served, monkeypatch, home):
    from harness import gateway_ledger_health
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full = True
    assert post(url, "/v1/messages", raw)[0] == 500

    def resume(_ledger):
        raise RuntimeError("planted by the test")
    monkeypatch.setattr(gateway_ledger_health, "resume", resume)
    assert post(url, "/v1/messages", raw)[0] == 503
    assert ledger.failed is not None and len(upstream.requests) == 2


def test_r6_the_gap_entry_names_the_entry_that_was_written_and_not_served(
        keyed, served, monkeypatch, home):
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
    assert post(url, "/v1/messages", raw)[0] == 500        # held back; its entry is on disk
    broken.on = False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = [entry for segment in gateway_ledger.check(home) for entry in segment["rows"]]
    assert [entry.kind for entry in rows] == [
        "endpoint_call", "endpoint_call", "ledger_gap", "endpoint_call"]
    gap, unserved = rows[2], rows[1]
    assert gap.meta["unconfirmed"] == [
        {"segment": "segment-000001.jsonl", "seq": unserved.seq, "kind": "endpoint_call",
         "entry_hash": unserved.entry_hash}]
    assert gateway_ledger_cli.main(["verify"]) == 0


def test_r6_a_gap_after_an_ordinary_failed_write_names_no_entry(
        keyed, served, monkeypatch, home):
    """Control: the write itself failed, nothing reached the disk, nothing is unconfirmed."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger, disk = _gateway(monkeypatch, served, turn2(3), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    disk.full = True
    assert post(url, "/v1/messages", raw)[0] == 500
    disk.full = False
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    rows = [entry for segment in gateway_ledger.check(home) for entry in segment["rows"]]
    gap, = [entry for entry in rows if entry.kind == "ledger_gap"]
    assert "unconfirmed" not in gap.meta
