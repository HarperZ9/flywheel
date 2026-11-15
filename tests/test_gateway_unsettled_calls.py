"""An unsettled call: reported, counted against its key, and settled by an operator.

Fifth review round of 2.0.0, the lead's ruling 1. A gateway that is killed
between a provider's reply and the ledger append now leaves the call's started
entry (tests/test_gateway_write_ahead.py). These tests cover what follows:

  report     `flywheel gateway-ledger verify` and `show` name the call, and
             exit 3 while it is unsettled;
  budget     the reservation the call took at admission counts against its key
             until the call is settled, across a gateway restart;
  settle     `flywheel gateway-ledger settle CALL` records what the operator
             says the provider billed, charges the key and frees the
             reservation: at once with no gateway running, and through a
             request file when one is;
  in flight  a call a running gateway is still making is `open`, not unsettled,
             and cannot be settled by hand.

The unsettled call in each test is made by a real child process that is killed
after the stub provider answered (tests/gateway_crash_child.py). No provider
is called.
"""
import json
import threading

import pytest

from harness import gateway_ledger, gateway_ledger_cli
from tests import gateway_messages_support as support
from tests.gateway_disk_support import gateway_on_disk, home  # noqa: F401  (fixture)
from tests.gateway_keys_support import keyed, post, served, turn2  # noqa: F401  (fixtures)
from tests.test_gateway_write_ahead import STARTED, _killed

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

RESERVED = 89                           # the child's call reserved 25 input and 64 output


def _unsettled(keys, where, **limits) -> str:
    """Leave one unsettled call for a new key `ci-bot`; returns the call id."""
    keys.create("ci-bot", **limits)
    with support.Upstream(turn2(1)) as upstream:
        _killed(where, upstream.url, keys, "after_reply")
        assert len(upstream.requests) == 1
    entry, = [e for segment in gateway_ledger.check(where) for e in segment["rows"]]
    assert entry.kind == STARTED and entry.meta["reserved"] == [25, 64]
    return entry.content


def _cli(capsys, *argv) -> tuple:
    capsys.readouterr()
    code = gateway_ledger_cli.main(list(argv))
    said = capsys.readouterr()
    return code, said.out, said.err


def _kinds(where) -> list:
    return [e.kind for segment in gateway_ledger.check(where) for e in segment["rows"]]


def test_verify_and_show_name_the_unsettled_call(keyed, home, capsys):
    keys, _store = keyed
    call = _unsettled(keys, home)
    code, out, _err = _cli(capsys, "verify")
    assert code == 3 and "gateway ledger verifies: 1 entries" in out
    assert f"UNSETTLED call {call}  key=ci-bot  endpoint=openai  reserved={RESERVED}" in out
    assert "1 unsettled call(s)" in out and "gateway-ledger settle" in out
    code, out, err = _cli(capsys, "show", "--unsettled", "--json")
    row, = [json.loads(line) for line in out.splitlines()]
    assert code == 3 and (row["kind"], row["content"], row["state"]) == (STARTED, call, "unsettled")
    assert "UNSETTLED" in err
    code, out, _err = _cli(capsys, "show")
    assert code == 3 and f"call={call}" in out and "state=UNSETTLED" in out


def test_control_a_ledger_whose_calls_all_ended_reports_none(keyed, served, monkeypatch, home,
                                                             capsys):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    assert post(url, "/v1/messages", raw)[0] == 200
    gateway_ledger.close_all()
    code, out, _err = _cli(capsys, "verify")
    assert code == 0 and "UNSETTLED" not in out and "open" not in out
    assert _cli(capsys, "show", "--unsettled")[:2] == (0, "")


def test_the_reservation_of_an_unsettled_call_counts_against_its_key_until_it_is_settled(
        keyed, served, monkeypatch, home, capsys):
    keys, _store = keyed
    call = _unsettled(keys, home, token_limit=80)       # the reservation alone is 89
    raw_row = keys.row("ci-bot")
    assert raw_row["totals"]["tokens"] == 0             # nothing was charged for the lost call
    raw = keys.store.saved["FLYWHEEL_GATEWAY_KEY@ci-bot"]
    url, upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    assert ledger.entries[-1].kind == "calls_unsettled"
    assert ledger.entries[-1].meta["calls"] == [call] and ledger.calls.held(
        raw_row["fingerprint"]) == (25, 64, 1)
    status, _headers, body = post(url, "/v1/messages", raw)
    assert status == 400 and upstream.requests == []
    said = body["error"]["message"]
    assert "has reached its token limit (89 of 80 tokens used)" in said
    assert "89 of those tokens are the reservations of 1 unsettled call(s)" in said
    assert "gateway-ledger settle" in said
    # The operator reads the provider's usage page: the call cost 10 in and 5 out.
    code, out, _err = _cli(capsys, "settle", call, "--input", "10", "--output", "5",
                           "--note", "read from the usage page")
    assert code == 0 and "a gateway is running" in out and f"settle-{call}.json" in out
    assert post(url, "/v1/messages", raw)[0] == 200     # the gateway applied it, then admitted
    assert len(upstream.requests) == 1
    assert keys.row("ci-bot")["totals"]["tokens"] == 15 + 460
    assert ledger.calls.held(raw_row["fingerprint"]) == (0, 0, 0)
    assert not list(gateway_ledger.folder(home).glob("settle-*"))
    gateway_ledger.close_all()
    assert _kinds(home) == [STARTED, "calls_unsettled", "endpoint_call_refused",
                            "endpoint_call_settled", STARTED, "endpoint_call"]
    settled = [e for s in gateway_ledger.check(home) for e in s["rows"]][3]
    assert settled.content == call and settled.meta == {
        "endpoint": "openai", "interface": "anthropic-messages", "key": "ci-bot",
        "key_fp": raw_row["fingerprint"], "prompt_sha": settled.meta["prompt_sha"],
        "call": call, "settled_by": "operator", "charged_tokens": 15, "input": 10, "output": 5,
        "note": "read from the usage page"}
    assert _cli(capsys, "verify")[0] == 0


def test_control_the_same_key_with_no_unsettled_call_is_served(keyed, served, monkeypatch, home):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=80)
    url, upstream, _ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 1


def test_settle_with_no_gateway_running_writes_the_entry_and_charges_the_key(
        keyed, home, capsys):
    keys, _store = keyed
    call = _unsettled(keys, home)
    assert _cli(capsys, "settle", "not-a-call-id")[0] == 2
    assert _cli(capsys, "settle", "0" * 24)[0] == 1                     # never started
    code, _out, err = _cli(capsys, "settle", call)
    assert code == 2 and "--input N --output N" in err and "--no-charge" in err
    assert _cli(capsys, "settle", call, "--input", "3")[0] == 2         # one count alone
    assert _cli(capsys, "settle", call, "--input", "3", "--output", "-1")[0] == 2
    assert _kinds(home) == [STARTED], "a refused settle wrote nothing"
    code, out, _err = _cli(capsys, "settle", call, "--input", "451", "--output", "9")
    assert code == 0 and f"call {call} settled; key 'ci-bot' was charged 460 tokens" in out
    assert keys.row("ci-bot")["totals"]["tokens"] == 460
    assert _kinds(home) == [STARTED, "calls_unsettled", "endpoint_call_settled"]
    assert _cli(capsys, "verify")[0] == 0
    code, _out, err = _cli(capsys, "settle", call, "--no-charge")       # a second time
    assert code == 1 and "has an end entry" in err
    assert keys.row("ci-bot")["totals"]["tokens"] == 460


def test_settle_with_no_charge_frees_the_reservation_and_charges_nothing(keyed, home, capsys):
    keys, _store = keyed
    call = _unsettled(keys, home)
    code, out, _err = _cli(capsys, "settle", call, "--no-charge")
    assert code == 0 and "was charged 0 tokens" in out
    assert keys.row("ci-bot")["totals"]["tokens"] == 0
    ledger = gateway_ledger.GatewayLedger(home)
    try:
        assert ledger.calls.held(keys.row("ci-bot")["fingerprint"]) == (0, 0, 0)
    finally:
        ledger.close()


def test_a_new_segment_carries_the_unsettled_call(keyed, home, monkeypatch):
    """A segment is self-contained: its header names the calls that were open before it."""
    keys, _store = keyed
    call = _unsettled(keys, home)
    fingerprint = keys.row("ci-bot")["fingerprint"]
    monkeypatch.setattr(gateway_ledger, "ROTATE_AT", 1)
    for number in (2, 3):                                               # two restarts
        ledger = gateway_ledger.GatewayLedger(home)
        try:
            assert ledger.path.name == f"segment-{number:06d}.jsonl"
            assert ledger.calls.held(fingerprint) == (25, 64, 1)
            assert ledger.entries[0].kind == "calls_unsettled"
        finally:
            ledger.close()
    found = gateway_ledger.check(home)
    assert all(segment["ok"] for segment in found), found
    assert [list(segment["header"].get("open_calls", {})) for segment in found] == [
        [], [call], [call]]


def test_a_call_in_flight_is_open_and_cannot_be_settled_by_hand(
        keyed, served, monkeypatch, home, capsys):
    from harness import endpoints_http
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger, _disk = gateway_on_disk(monkeypatch, served, turn2(1), home)
    reached, go, real = threading.Event(), threading.Event(), endpoints_http._guard

    def guard(transport, *args, **kwargs):
        reached.set()
        assert go.wait(30), "the test never released the call"
        return real(transport, *args, **kwargs)
    monkeypatch.setattr(endpoints_http, "_guard", guard)
    answers = []
    worker = threading.Thread(target=lambda: answers.append(post(url, "/v1/messages", raw)[0]))
    worker.start()
    try:
        assert reached.wait(30)
        call = ledger.entries[-1].content
        assert ledger.entries[-1].kind == STARTED
        assert ledger.calls.held(keys.row("ci-bot")["fingerprint"]) == (0, 0, 0)
        code, out, _err = _cli(capsys, "verify")
        assert code == 0 and "UNSETTLED" not in out and f"open call {call}" in out
        code, _out, err = _cli(capsys, "settle", call, "--no-charge")
        assert code == 1 and "is open" in err
    finally:
        go.set()
        worker.join(30)
    assert answers == [200] and support.kinds(ledger) == ["endpoint_call"]
