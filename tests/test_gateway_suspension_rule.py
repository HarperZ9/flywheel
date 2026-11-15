"""One rule for suspending a key: its call reached the provider and was not fully accounted.

Fifth review round of 2.0.0, the lead's ruling 4. Before it the rule had two
halves that did not meet. A fault nobody planned for (`accounting_error`) and
a delivered stream that could not be charged or recorded suspended the key. A
plain reply whose debit failed (`charge_failed`) did not, although the
provider had billed a call the key's totals do not show, and the key holder
could send the next one. An unfinished stream whose part charge failed did
not either.

The rule now: a call that reached the provider is accounted when its key was
charged and its end entry was written. When either step fails, for any
reason, the key is suspended until `flywheel gateway-key clear NAME`. The
threat is unrecorded spend: a key whose totals or whose ledger miss a call
must not make another until an operator has read the ledger.

What does not suspend: a failure of the provider (an error status, a cut
stream, a malformed reply), a refusal before contact, and the gateway token,
which has no budget to protect.

A real gateway on a loopback port, a stub upstream, keys in the in-memory
store. No provider is called.
"""
import pytest

from harness import gateway_key_cli, gateway_keys
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

PATH = "/v1/messages"


class Planted(RuntimeError):
    """A fault no handler in the gateway names."""


def _debit_fails(monkeypatch):
    def debit(self, *args, **kwargs):
        raise gateway_keys.KeysError("the gateway key list is locked by another process")
    monkeypatch.setattr(gateway_keys.Keys, "debit", debit)


def _append_fails(monkeypatch):
    """The ledger refuses a served call's entry and takes the failure entry."""
    from harness.local_session import SessionLedger
    real = SessionLedger.append

    def append(self, kind, content, meta=None):
        if kind == "endpoint_call":
            raise OSError(28, "No space left on device")
        return real(self, kind, content, meta)
    monkeypatch.setattr(SessionLedger, "append", append)


def _unplanned(monkeypatch):
    from harness import gateway_turn

    def reply_text(_reply):
        raise Planted("planted by the test")
    monkeypatch.setattr(gateway_turn, "reply_text", reply_text)


def _whole(stream: bool):
    return (support.stream_answer(stream_bytes("openai", "turn2")) if stream
            else turn2(1)[0])


def _cut(_stream: bool):
    whole = stream_bytes("openai", "turn2")
    return support.stream_answer(whole[:len(whole) // 2])


# name -> (the fault, the upstream's answer, streamed, the reason the entry carries)
CASES = {
    "plain reply, debit failed": (_debit_fails, _whole, False, "charge_failed"),
    "plain reply, entry refused": (_append_fails, _whole, False, "ledger_failed"),
    "stream, debit failed": (_debit_fails, _whole, True, "delivered_unrecorded_charge"),
    "stream, entry refused": (_append_fails, _whole, True, "delivered_unrecorded_charge"),
    "plain reply, unplanned fault": (_unplanned, _whole, False, "accounting_error"),
    "stream, unplanned fault": (_unplanned, _whole, True, "delivered_unrecorded_charge"),
    "cut stream, part charge failed": (_debit_fails, _cut, True, "stream_incomplete"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_a_call_that_reached_the_provider_and_was_not_fully_accounted_suspends_its_key(
        keyed, served, monkeypatch, case):
    fault, answer, stream, reason = CASES[case]
    keys, store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served([answer(stream), *turn2(2)])
    with monkeypatch.context() as planted:
        fault(planted)
        status, _headers, body = post(url, PATH, raw, {**BODIES[PATH], "stream": stream})
    assert len(upstream.requests) == 1, "the call reached the provider"
    assert status == (200 if stream else 500)           # a stream's text had left
    entry, = support.recorded(ledger)
    assert (entry.kind, entry.meta["reason"]) == ("endpoint_call_failed", reason)
    row = keys.row("ci-bot")
    assert "suspended" in row, f"{case}: the key was not suspended"
    assert row["suspended"]["reason"] in (reason, "charge_failed")
    # The fault is gone. The key still makes no call until an operator clears it.
    refused, _headers, said = post(url, PATH, raw)
    assert refused == 403 and "suspended" in said["error"]["message"]
    assert "gateway-key clear ci-bot" in said["error"]["message"]
    assert len(upstream.requests) == 1, "a suspended key reaches no upstream"
    assert gateway_key_cli.main(["clear", "ci-bot"], store=store,
                                environ={"FLYWHEEL_HOME": str(keys.path.parent)}) == 0
    assert post(url, PATH, raw)[0] == 200 and len(upstream.requests) == 2


@pytest.mark.parametrize("case", ["plain reply, debit failed", "stream, debit failed",
                                  "cut stream, part charge failed"])
def test_an_entry_for_a_charge_that_failed_says_nothing_was_charged(
        keyed, served, monkeypatch, case):
    """The entry of a failed debit used to carry the tokens as `charged_tokens`."""
    fault, answer, stream, _reason = CASES[case]
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served([answer(stream)])
    fault(monkeypatch)
    post(url, PATH, raw, {**BODIES[PATH], "stream": stream})
    entry, = support.recorded(ledger)
    assert entry.meta["charged_tokens"] == 0 and entry.meta["uncharged_tokens"] > 0
    assert keys.row("ci-bot")["totals"]["tokens"] == 0


FAILURES = {
    "provider error": lambda: support.json_answer({"error": {"message": "overloaded"}}, 529),
    "cut stream": lambda: _cut(True),
    "malformed reply": lambda: support.json_answer({"choices": "not a list"}),
}


@pytest.mark.parametrize("what", list(FAILURES))
def test_control_a_failure_of_the_provider_suspends_nothing(keyed, served, what):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served([FAILURES[what](), *turn2(1)])
    post(url, PATH, raw, {**BODIES[PATH], "stream": what == "cut stream"})
    entry, = support.recorded(ledger)
    assert entry.kind == "endpoint_call_failed" and len(upstream.requests) == 1
    assert "suspended" not in keys.row("ci-bot")
    assert post(url, PATH, raw)[0] == 200


def test_control_the_gateway_token_is_not_suspended_by_the_same_fault(served, monkeypatch):
    url, upstream, ledger = served(turn2(2))
    with monkeypatch.context() as planted:
        _append_fails(planted)
        assert post(url, PATH, support.TOKEN)[0] == 500
    assert post(url, PATH, support.TOKEN)[0] == 200 and len(upstream.requests) == 2
    assert support.kinds(ledger) == ["endpoint_call_failed", "endpoint_call"]
