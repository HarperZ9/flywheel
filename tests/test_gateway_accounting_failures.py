"""No reply without a record: a debit or a ledger append that fails.

The upstream has answered. If the key cannot be charged or the entry cannot be
appended, the gateway still leaves an `endpoint_call_failed` entry that says
so, and tells the client. A plain reply is not served. A stream's text has
already left, so its entry says `delivered_unrecorded_charge` and the key is
suspended until an operator clears it with `flywheel gateway-key clear NAME`.

A real gateway on a loopback port, a stub upstream replaying recorded replies,
keys in the in-memory store. No provider is called.
"""
import pytest

from harness import gateway_key_cli, gateway_keys
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, post, served, stream_bytes, turn2)

PATHS = ["/v1/messages", "/v1/responses"]


def _failing_debit(monkeypatch) -> dict:
    """Make every debit fail while the returned switch says so."""
    switch, real = {"fail": True}, gateway_keys.Keys.debit

    def debit(self, *args, **kwargs):
        if switch["fail"]:
            raise gateway_keys.KeysError("the gateway key list is locked by another process")
        return real(self, *args, **kwargs)
    monkeypatch.setattr(gateway_keys.Keys, "debit", debit)
    return switch


@pytest.mark.parametrize("path", PATHS)
def test_a_plain_reply_that_cannot_be_charged_is_not_served_and_is_recorded(
        keyed, served, monkeypatch, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served(turn2(1))
    _failing_debit(monkeypatch)
    status, _headers, body = post(url, path, raw)
    assert status == 500 and "was not served" in body["error"]["message"]
    assert "could not be charged" in body["error"]["message"]
    assert len(upstream.requests) == 1
    entry, = ledger.entries
    assert (entry.kind, entry.meta["reason"]) == ("endpoint_call_failed", "charge_failed")
    assert entry.meta["key"] == "ci-bot" and entry.meta["delivered"] is False
    assert len(entry.meta["response_sha"]) == 16, "the hash the served entry would carry"
    assert "suspended" not in keys.row("ci-bot")


@pytest.mark.parametrize("path", PATHS)
def test_a_delivered_stream_that_cannot_be_charged_is_recorded_and_suspends_the_key(
        keyed, served, monkeypatch, path):
    keys, store = keyed
    raw, _ = keys.create("ci-bot")
    answers = [support.stream_answer(stream_bytes("openai", "turn2"))] + turn2(2)
    url, upstream, ledger = served(answers)
    switch = _failing_debit(monkeypatch)
    status, _headers, body = post(url, path, raw, {**BODIES[path], "stream": True})
    assert status == 200
    assert b"text_delta" in body or b"output_text.delta" in body, "text was delivered"
    assert b"delivered_unrecorded_charge" in body and b"gateway-key clear ci-bot" in body
    assert b"message_stop" not in body and b"response.completed" not in body
    entry, = ledger.entries
    assert entry.kind == "endpoint_call_failed"
    assert entry.meta["reason"] == "delivered_unrecorded_charge"
    assert entry.meta["cause"] == "charge_failed" and entry.meta["delivered"] is True
    assert entry.meta["key"] == "ci-bot" and entry.meta["charged_tokens"] == 460

    switch["fail"] = False                  # the debit works again; the key stays stopped
    refused, _headers, body = post(url, path, raw)
    assert refused == 403 and "suspended" in body["error"]["message"]
    assert len(upstream.requests) == 1, "a suspended key reaches no upstream"
    assert ledger.entries[-1].meta["reason"] == "key_suspended"
    assert gateway_key_cli.main(["clear", "ci-bot"], store=store,
                                environ={"FLYWHEEL_HOME": str(keys.path.parent)}) == 0
    assert post(url, path, raw)[0] == 200


def test_control_a_stream_whose_debit_works_ends_normally_and_suspends_nothing(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    status, _headers, body = post(url, "/v1/messages", raw,
                                  {**BODIES["/v1/messages"], "stream": True})
    assert status == 200 and b"message_stop" in body
    assert support.kinds(ledger) == ["endpoint_call"]
    assert "suspended" not in keys.row("ci-bot")


class _Refusing:
    """A ledger whose append fails for a served call and works for a failure."""

    def __init__(self):
        self.entries = []

    def append(self, kind, content, meta=None):
        if kind == "endpoint_call":
            raise OSError("disk full")
        self.entries.append((kind, content, meta))


@pytest.mark.parametrize("path", PATHS)
def test_a_reply_whose_ledger_append_fails_is_not_served(served, monkeypatch, path):
    from harness import gateway
    url, _upstream, _ledger = served(turn2(1))
    ledger = _Refusing()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    status, _headers, body = post(url, path, support.TOKEN)
    assert status == 500 and "could not be recorded" in body["error"]["message"]
    (kind, reason, meta), = ledger.entries
    assert (kind, reason, meta["key"]) == ("endpoint_call_failed", "ledger_failed", "owner")
