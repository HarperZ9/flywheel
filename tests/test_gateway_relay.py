"""A gateway's worker process records in the gateway's ledger through the parent.

Sixth review round of 2.0.0 (finding S1). The worker of a v1 subagent swarm is
a separate process and one process writes a home's ledger, so the worker
sends each entry to the gateway that started it (harness/gateway_ledger_relay).
tests/test_gateway_route_accounting.py runs a real worker process end to end.
These tests hold the relay's own rules, with the child's side called in this
process:

  - the parent answers after the entry is in the ledger;
  - a child may append a started entry and one end for a call it started,
    and nothing else;
  - a child that ends with a call still open leaves it named unsettled;
  - with no ledger the child is told and its call is not made.

The last test is about /v1/embeddings, the other route whose body now comes
from the grant step: the gateway's own fields are not sent to the provider.
"""
import json
import urllib.request

import pytest

from harness import (gateway, gateway_calls, gateway_embeddings, gateway_ledger,
                     gateway_ledger_relay as relay, gateway_reach)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
A, B = "a" * 24, "b" * 24


@pytest.fixture
def parent(tmp_path, monkeypatch):
    """(ledger, child): a gateway process and the ledger its child process would hold."""
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    gateway_reach.enforce(lambda: ledger)
    env = {}
    token = relay.issue(env)
    assert token and env[relay.ADDR].startswith("127.0.0.1:")
    yield ledger, relay.RelayLedger(env[relay.ADDR], env[relay.TOKEN]), token
    ledger.close()


def started(call):
    return gateway_calls.STARTED, call, {"endpoint": "openai", "prompt_sha": "p" * 16, "call": call}


def test_an_entry_is_in_the_ledger_when_the_child_gets_its_answer(parent):
    ledger, child, _token = parent
    child.append(*started(A))
    entry, = ledger.entries
    assert (entry.kind, entry.content, entry.meta["via"]) == (
        gateway_calls.STARTED, A, "subagent_worker")
    child.append("endpoint_call", "r" * 16, {"endpoint": "openai", "prompt_sha": "p" * 16,
                                             "call": A})
    assert [e.kind for e in ledger.entries] == [gateway_calls.STARTED, "endpoint_call"]


@pytest.mark.parametrize("kind, content, meta", [
    ("endpoint_call", "r" * 16, {"call": B}),               # an end for a call it did not start
    ("endpoint_call_settled", A, {"call": A}),              # a kind a child may not write
    ("calls_unsettled", "x", {"call": A}),
    ("endpoint_call_refused", "x", {"call": A}),
    ("endpoint_call_started", A, {"call": B}),              # content is not the call id
    ("endpoint_call_started", A, {}),                       # names no call
])
def test_a_child_may_write_only_a_start_and_the_end_of_its_own_call(parent, kind, content, meta):
    ledger, child, _token = parent
    child.append(*started(A))
    with pytest.raises(relay.RelayRefused):
        child.append(kind, content, meta)
    assert len(ledger.entries) == 1


def test_a_child_cannot_write_a_key_or_a_reservation_into_the_ledger(parent):
    """A started entry that named a virtual key and a reservation would be counted against
    that key once its call was unsettled. The parent keeps the fields a call made with the
    gateway token has and drops the rest."""
    ledger, child, token = parent
    kind, content, meta = started(A)
    child.append(kind, content, {**meta, "key": "ci-bot", "key_fp": "f" * 16,
                                 "reserved": [10 ** 9, 10 ** 9], "charged_tokens": -5,
                                 "interface": "anthropic-messages"})
    entry, = ledger.entries
    assert entry.meta == {**meta, "via": "subagent_worker"}
    relay.closed(token)                 # the child is gone: the call is unsettled
    assert gateway_calls.held(ledger, "f" * 16) == (0, 0, 0)


def test_a_call_id_is_started_once_and_ended_once(parent):
    ledger, child, _token = parent
    child.append(*started(A))
    with pytest.raises(relay.RelayRefused):
        child.append(*started(A))
    child.append("endpoint_call_failed", "upstream_error", {"call": A, "endpoint": "openai",
                                                            "prompt_sha": "p" * 16})
    with pytest.raises(relay.RelayRefused):
        child.append("endpoint_call", "r" * 16, {"call": A})
    assert len(ledger.entries) == 2


def test_an_unknown_token_is_refused(parent):
    ledger, child, _token = parent
    stranger = relay.RelayLedger("127.0.0.1:%d" % child._where[1], "0" * 64)
    with pytest.raises(relay.RelayRefused):
        stranger.append(*started(A))
    assert ledger.entries == []


def test_a_child_that_ends_with_a_call_open_leaves_it_named_unsettled(parent):
    ledger, child, token = parent
    child.append(*started(A))
    child.append(*started(B))
    child.append("endpoint_call", "r" * 16, {"call": B, "endpoint": "openai",
                                             "prompt_sha": "p" * 16})
    assert relay.closed(token) == [A]
    marker = ledger.entries[-1]
    assert marker.kind == "calls_unsettled" and marker.meta == {"reason": "child_ended",
                                                               "calls": [A]}
    assert A in ledger.calls.orphans
    with pytest.raises(relay.RelayRefused):         # the token is gone with the child
        child.append(*started("c" * 24))


def test_with_no_ledger_the_child_is_told_and_nothing_is_written(parent):
    ledger, child, _token = parent
    gateway_reach.enforce(lambda: None)             # the gateway's ledger is unavailable
    with pytest.raises(relay.RelayRefused):
        child.append(*started(A))
    assert ledger.entries == []


def test_outside_a_gateway_no_relay_is_issued():
    gateway_reach.release()
    env = {}
    assert relay.issue(env) == "" and env == {}
    assert relay.adopt({}) is False


def test_embeddings_does_not_forward_the_gateways_own_fields(monkeypatch):
    """Over HTTP the body of /v1/embeddings is the operation the grant step admitted, which
    carries `data_refs` and `credential_refs`. They stay in the gateway."""
    from dataclasses import replace

    from harness import providers
    from harness.local_session import SessionLedger
    ledger, sent = SessionLedger(), []
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    monkeypatch.setitem(providers.REGISTRY, "xprov", replace(
        providers.REGISTRY["openai"], base_url="http://provider.invalid/v1", api_key_env=""))

    class Answer:
        status = 200

        def read(self):
            return b'{"data":[{"embedding":[0.1]}],"usage":{"prompt_tokens":2}}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout=60):
        sent.append(json.loads(request.data))
        return Answer()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    _body, code = gateway_embeddings.openai_embeddings(
        {"model": "xprov:embed-3", "input": "hi", "data_refs": [], "credential_refs": []},
        providers_registry=providers.REGISTRY, urllib_module=urllib,
        resolve_credential=lambda name: "", ledger_of=gateway._router_ledger)
    assert code == 200 and sent == [{"model": "embed-3", "input": "hi"}]
    start, end = ledger.entries
    assert start.meta["endpoint"] == end.meta["endpoint"] == "xprov"
    assert end.meta["model_ref"] == "xprov:embed-3"
