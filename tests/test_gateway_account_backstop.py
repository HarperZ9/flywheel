"""The backstop: a call that contacted its provider and reached no end still gets one.

Sixth review round of 2.0.0. The fourth independent review removed
`Account.settle` and no test failed: the backstop had none. `settle` is what
`gateway_turn_call.Stream.close` calls when a stream ends, whatever ended it.
An account that contacted an upstream and was closed by none of `served`,
`failed` and `lost` is closed there with a failed entry, and a virtual key is
suspended, because the cause is unknown.

No request path is known to reach it; that is what a backstop is for. These
tests put an account in that state directly: contacted, then the stream
closed with nothing recorded.
"""
import pytest

from harness import gateway_account, gateway_key_gate, gateway_turn, gateway_turn_call
from harness.local_session import SessionLedger
from tests import gateway_messages_support as support

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


class Keys:
    """A key list that records what it is asked to mark."""

    def __init__(self):
        self.marked = []

    def mark(self, name, **fields):
        self.marked.append((name, fields))
        return {}


def contacted(caller=None):
    """(account, ledger, stream): an account that reached its provider and recorded nothing."""
    ledger = SessionLedger()
    turn = gateway_turn.Turn("anthropic-messages", "claude-sonnet-5",
                             messages=[{"role": "user", "text": "What changed?"}],
                             caller=caller)
    upstream = gateway_turn.Upstream("openai", "openai", object())
    account = gateway_account.Account(ledger, upstream, turn)
    assert account.reach(lambda: "sent") == "sent" and account.state == "contacted"
    return account, ledger, gateway_turn_call.Stream((event for event in ()), None, account)


def test_a_stream_closed_with_nothing_recorded_gets_a_failed_entry():
    account, ledger, stream = contacted()
    stream.close()
    end, = support.recorded(ledger)
    assert end.kind == "endpoint_call_failed" and account.state == "closed"
    assert end.meta["reason"] == "delivered_unrecorded_charge"
    assert end.meta["cause"] == "accounting_error" and end.meta["delivered"] is True
    assert end.meta["call"] == ledger.entries[0].content


def test_the_backstop_suspends_a_virtual_key(monkeypatch):
    from harness import gateway_key_policy
    monkeypatch.setattr(gateway_key_policy, "_HELD", {})
    keys = Keys()
    row = {"fingerprint": "f" * 16, "totals": {}}
    caller = gateway_key_gate.Caller("ci-bot", "f" * 16, row, keys, ticket=[25, 64])
    _account, ledger, stream = contacted(caller)
    stream.close()
    end, = support.recorded(ledger)
    assert end.meta["key"] == "ci-bot" and end.meta["reason"] == "delivered_unrecorded_charge"
    assert "charged_tokens" not in end.meta         # what the key was charged is not known
    (name, fields), = keys.marked
    assert name == "ci-bot" and fields["suspended"]["reason"] == "delivered_unrecorded_charge"
    assert gateway_key_policy.suspended(caller) == "delivered_unrecorded_charge"


def test_control_an_account_that_was_recorded_gets_no_second_entry():
    account, ledger, stream = contacted()
    account.failed("upstream_error", "the provider closed the connection")
    stream.close()
    end, = support.recorded(ledger)
    assert end.meta["reason"] == "upstream_error"


def test_control_an_account_that_never_contacted_gets_no_entry():
    ledger = SessionLedger()
    turn = gateway_turn.Turn("anthropic-messages", "claude-sonnet-5",
                             messages=[{"role": "user", "text": "What changed?"}])
    account = gateway_account.Account(ledger, gateway_turn.Upstream("openai", "openai", object()),
                                      turn)
    gateway_turn_call.Stream((event for event in ()), None, account).close()
    assert ledger.entries == [] and account.state == "open"


# --- the in-process stop and the clock (review 4, S7) --------------------------------------

class Unwritable:
    """A key list that cannot be written, and reads as the row it was given."""

    def __init__(self, row):
        self.held = row

    def mark(self, *args, **kwargs):
        raise OSError("the key list cannot be written")

    def row(self, name):
        return self.held


def test_a_clock_set_back_does_not_lift_a_stop_held_in_the_gateway(monkeypatch):
    """A key an operator cleared once; the clock is then set back; a suspension follows whose
    key-list write fails. The stop is held in the process. It compared wall-clock times, so
    the earlier clear, now 'later' on the clock, lifted it."""
    from harness import gateway_key_policy as policy
    monkeypatch.setattr(policy, "_HELD", {})
    now = [2_000_000_000.0]
    monkeypatch.setattr(policy.time, "time", lambda: now[0])
    row = {"cleared": 2_000_000_100.0, "clears": 1, "totals": {}}    # cleared once, earlier
    caller = gateway_key_gate.Caller("k", "fp-clock", row, Unwritable(row))
    now[0] = 2_000_000_050.0            # the clock went back 50 s before that clear
    policy.suspend(caller, "charge_failed")
    assert policy.suspended(caller) == "charge_failed"


def test_control_a_clear_after_the_stop_lifts_it_whatever_the_clock_says(monkeypatch):
    from harness import gateway_key_policy as policy
    monkeypatch.setattr(policy, "_HELD", {})
    now = [2_000_000_000.0]
    monkeypatch.setattr(policy.time, "time", lambda: now[0])
    row = {"clears": 1, "totals": {}}
    caller = gateway_key_gate.Caller("k", "fp-clock", row, Unwritable(row))
    policy.suspend(caller, "charge_failed")
    assert policy.suspended(caller) == "charge_failed"
    now[0] = 1_000_000_000.0            # the clock is far behind when the operator clears
    later = gateway_key_gate.Caller("k", "fp-clock", {"clears": 2, "cleared": now[0],
                                                     "totals": {}}, Unwritable(row))
    assert policy.suspended(later) is None
