"""No upstream contact without accounting: the invariant, by fault injection.

One failure is planted at one step of a model call, for every step this file
names. Whatever the step:

  no upstream request    then no reply was served and the key was not charged;
  an upstream request    then the ledger has exactly one entry for it, and the key
                         was charged or is suspended (or, for a plain reply whose
                         debit failed, the reply was held back and the entry says
                         `charge_failed`). A reply is served only when that entry
                         is `endpoint_call`.

The last group checks that each transport call is made inside an `Account`
(harness/gateway_account.py): a path added later that contacts an upstream
without one fails there.

A real gateway on a loopback port, a stub upstream replaying recorded replies,
keys in the in-memory store. No provider is called.
"""
import pytest

from tests import gateway_messages_support as support
from tests.gateway_contact_support import PATHS, calls, raw_post, sent
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, plain_object, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


class Injected(RuntimeError):
    """The fault a test plants. No handler in the gateway names it."""


def _raiser(*_args, **_kwargs):
    raise Injected("planted by the test")


def _after(count: int, real):
    """`real` for the first `count` calls, then the planted fault."""
    seen = []

    def wrapped(*args, **kwargs):
        seen.append(1)
        if len(seen) > count:
            raise Injected("planted by the test")
        return real(*args, **kwargs)
    return wrapped


def _plant(module: str, name: str, value=_raiser, owner: str = ""):
    """A fault: replace `module.name` (or `module.owner.name`) when the test asks."""
    def fault(monkeypatch):
        import importlib
        target = importlib.import_module(f"harness.{module}")
        target = getattr(target, owner) if owner else target
        monkeypatch.setattr(target, name, value(getattr(target, name)) if value is _later
                            else value)
    return fault


def _later(real):
    return _after(1, real)


def _fault_feed(monkeypatch):
    from harness import endpoints_assemble
    for name in ("OpenAIAssembler", "AnthropicAssembler", "GeminiAssembler"):
        kind = getattr(endpoints_assemble, name)
        monkeypatch.setattr(kind, "feed", _after(2, kind.feed))


def _fault_append(monkeypatch):
    """The ledger refuses a served call's entry with an error that is not an OSError."""
    from harness.local_session import SessionLedger
    real = SessionLedger.append

    def append(self, kind, content, meta=None):
        if kind == "endpoint_call":
            raise Injected("planted by the test")
        return real(self, kind, content, meta)
    monkeypatch.setattr(SessionLedger, "append", append)


BEFORE = {
    "text form": _plant("gateway_turn", "_text_form"),
    "first hash": _plant("proposer", "prompt_hash"),
    "upstream choice": _plant("gateway_turn", "resolve_upstream"),
    "request body": _plant("gateway_turn_wire", "request"),
    "caller fields": _plant("gateway_key_gate", "meta", property(_raiser), "Caller"),
    "account": _plant("gateway_account", "__init__", _raiser, "Account"),
}
AFTER = {
    "reply read": _plant("gateway_turn_call", "read"),
    "reply text": _plant("gateway_turn", "reply_text"),
    "later hash": _plant("proposer", "prompt_hash", _later),
    "bill": _plant("gateway_key_gate", "__init__", _raiser, "Bill"),
    "settle": _plant("gateway_key_gate", "settle", _raiser, "Bill"),
    "debit": _plant("gateway_keys", "debit", _raiser, "Keys"),
    "provider tools": _plant("gateway_unaccounted", "provider_tools"),
    "record": _plant("gateway_turn", "record"),
    "usage": _plant("gateway_turn_call", "_usage"),
    "append": _fault_append,
}
STREAM_ONLY = {
    "stream end": _plant("endpoints_stream", "_finished"),
    "event feed": _fault_feed,
}


def _one_call(keyed, served, monkeypatch, path, stream, fault, provider="openai"):
    """Plant `fault`, send one request; (status, body, keys, upstream, ledger)."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    answer = (support.stream_answer(stream_bytes(provider, "turn2")) if stream
              else support.json_answer(plain_object(provider, "turn2")))
    url, upstream, ledger = served([answer], provider)
    fault(monkeypatch)
    status, body = raw_post(url, path, raw, sent(path, stream))
    return status, body, keys, upstream, ledger


def _delivered(status: int, body: bytes, stream: bool) -> bool:
    """Was a whole reply served: a 200 body, or a stream that reached its last event."""
    if not stream:
        return status == 200
    return status == 200 and (b"message_stop" in body or b"response.completed" in body)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("step", list(BEFORE))
def test_a_fault_before_contact_sends_nothing_and_serves_nothing(
        keyed, served, monkeypatch, path, stream, step):
    status, body, keys, upstream, ledger = _one_call(
        keyed, served, monkeypatch, path, stream, BEFORE[step])
    assert upstream.requests == [], f"a fault at {step!r} still reached the upstream"
    assert not _delivered(status, body, stream) and status >= 400
    assert keys.row("ci-bot")["totals"]["tokens"] == 0
    assert calls(ledger) == []


# Every step after contact on both deliveries, and the two stream steps on a stream.
AFTER_CASES = ([(step, stream) for step in AFTER for stream in (False, True)]
               + [(step, True) for step in STREAM_ONLY])


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("step,stream", AFTER_CASES)
def test_a_fault_after_contact_leaves_one_entry_and_a_charge_or_a_stopped_key(
        keyed, served, monkeypatch, path, stream, step):
    status, body, keys, upstream, ledger = _one_call(
        keyed, served, monkeypatch, path, stream, {**AFTER, **STREAM_ONLY}[step])
    assert len(upstream.requests) == 1
    entries = calls(ledger)
    assert len(entries) == 1, f"a fault at {step!r} left {[e.kind for e in entries]}"
    entry, row = entries[0], keys.row("ci-bot")
    assert entry.meta["key"] == "ci-bot" and len(entry.meta["prompt_sha"]) == 16
    # One case is neither: the debit itself failed on a plain call. The key list could not
    # be written, the reply was held back, and the entry says `charge_failed`
    # (test_gateway_accounting_failures.py). Nothing was served for it.
    held_back = (entry.meta.get("reason") == "charge_failed" and status == 500
                 and entry.meta["delivered"] is False)
    assert row["totals"]["tokens"] > 0 or "suspended" in row or held_back, (
        f"a fault at {step!r}: the provider was called, the key was not charged and is "
        "not suspended")
    if _delivered(status, body, stream):
        assert entry.kind == "endpoint_call"
    else:
        assert entry.kind == "endpoint_call_failed" and entry.meta.get("reason")
    assert ledger.verify()


@pytest.mark.parametrize("path", PATHS)
def test_a_fault_while_recording_a_cut_stream_still_leaves_one_entry(
        keyed, served, monkeypatch, path):
    """The upstream cut the stream, and the code that charges for the part received fails."""
    from harness import gateway_unaccounted
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    whole = stream_bytes("openai", "turn2")
    url, upstream, ledger = served([support.stream_answer(whole[:len(whole) // 2])])
    monkeypatch.setattr(gateway_unaccounted, "partial_charge", _raiser)
    status, _body = raw_post(url, path, raw, sent(path, True))
    assert status == 200 and len(upstream.requests) == 1
    entry, = calls(ledger)
    assert entry.kind == "endpoint_call_failed"
    assert entry.meta["cause"] == "accounting_error" and entry.meta["error"] == "Injected"
    assert "suspended" in keys.row("ci-bot")


def test_control_with_no_fault_the_same_calls_are_served_and_charged(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2")),
                                    *turn2(1)])
    for stream in (True, False):
        status, body = raw_post(url, "/v1/messages", raw, sent("/v1/messages", stream))
        assert _delivered(status, body, stream)
    assert support.kinds(ledger) == ["endpoint_call"] * 2 and len(upstream.requests) == 2
    row = keys.row("ci-bot")
    assert row["totals"]["tokens"] == 920 and "suspended" not in row


# --- Every contact is made inside an account -----------------------------------------------

def _watch_contacts(monkeypatch) -> list:
    """Record what `gateway_account.contacting()` says each time a transport is called."""
    from harness import endpoints_http, endpoints_stream, gateway_account
    seen = []

    def watched(real):
        def guard(transport, *args, **kwargs):
            who = gateway_account.contacting()
            seen.append(who if who == gateway_account.UNBILLED else
                        (type(who).__name__, getattr(who, "state", None)))
            return real(transport, *args, **kwargs)
        return guard
    monkeypatch.setattr(endpoints_http, "_guard", watched(endpoints_http._guard))
    monkeypatch.setattr(endpoints_stream, "_guard", watched(endpoints_stream._guard))
    return seen


STREAM_OPTIONS = {"error": {"message": "Unrecognized request argument supplied: stream_options",
                            "type": "invalid_request_error"}}


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("path", PATHS)
def test_every_upstream_contact_of_a_model_call_is_made_inside_an_account(
        keyed, served, monkeypatch, path, stream, provider):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    answer = (support.stream_answer(stream_bytes(provider, "turn2")) if stream
              else support.json_answer(plain_object(provider, "turn2")))
    url, upstream, ledger = served([answer], provider)
    seen = _watch_contacts(monkeypatch)
    status, _body = raw_post(url, path, raw, sent(path, stream))
    assert status == 200 and len(upstream.requests) == 1
    assert seen == [("Account", "contacted")]
    assert support.kinds(ledger) == ["endpoint_call"]


def test_a_retried_request_contacts_the_upstream_twice_inside_one_account(
        keyed, served, monkeypatch):
    """A stream the host refuses for `stream_options` is sent once more: one call, one entry."""
    from harness import endpoints_stream
    monkeypatch.setattr(endpoints_stream, "_NO_STREAM_OPTIONS", set())
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served([support.json_answer(STREAM_OPTIONS, 400),
                                    support.stream_answer(stream_bytes("openai", "turn2"))])
    seen = _watch_contacts(monkeypatch)
    status, body = raw_post(url, "/v1/messages", raw, sent("/v1/messages", True))
    assert status == 200 and b"message_stop" in body
    assert len(upstream.requests) == 2 and seen == [("Account", "contacted")] * 2
    assert support.kinds(ledger) == ["endpoint_call"]
    assert keys.row("ci-bot")["totals"]["calls"] == 1


def test_a_retried_plain_request_is_one_account_too(keyed, served, monkeypatch):
    """An Anthropic upstream that refuses `temperature` is asked once more without it."""
    from harness import endpoints
    monkeypatch.setattr(endpoints, "_NO_TEMPERATURE", set())
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    refusal = {"type": "error", "error": {"type": "invalid_request_error",
                                          "message": "`temperature` is deprecated for this model."}}
    url, upstream, ledger = served([support.json_answer(refusal, 400),
                                    support.json_answer(plain_object("anthropic", "turn2"))],
                                   "anthropic")
    seen = _watch_contacts(monkeypatch)
    status, _headers, _body = post(url, "/v1/messages", raw,
                                   {**BODIES["/v1/messages"], "temperature": 0.2})
    assert status == 200 and len(upstream.requests) == 2
    assert seen == [("Account", "contacted")] * 2 and support.kinds(ledger) == ["endpoint_call"]
    assert keys.row("ci-bot")["totals"]["calls"] == 1


def test_token_counting_is_the_one_contact_made_outside_an_account_and_it_says_so(
        served, monkeypatch):
    url, upstream, ledger = served([support.json_answer({"input_tokens": 12})], "anthropic")
    seen = _watch_contacts(monkeypatch)
    status, _headers, body = post(url, "/v1/messages/count_tokens", support.TOKEN,
                                  BODIES["/v1/messages"])
    assert status == 200 and body == {"input_tokens": 12}
    assert seen == ["unbilled"] and ledger.entries == [] and len(upstream.requests) == 1


def test_control_a_contact_outside_an_account_is_seen_by_the_watch(monkeypatch):
    """Control for the tests above: the watch reports a bare transport call as one."""
    from harness import endpoints_http
    seen = _watch_contacts(monkeypatch)
    endpoints_http._guard(lambda *args: (200, {}), "POST", "http://127.0.0.1:9", {}, b"{}",
                          1.0, "bare")
    assert seen == [("NoneType", None)]
