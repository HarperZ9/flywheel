"""Who a virtual key is, where it is accepted, and what its allow-list permits.

A real gateway on a loopback port and keys in the in-memory store. The control
in each route test sends the gateway's own token down the same path, so a 401
for the virtual key is shown to come from the key and not from the route.
"""
import http.client
import json
from urllib.parse import urlparse

import pytest

from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, keyed, post, served, turn2)

PATHS = ["/v1/messages", "/v1/responses"]


def _send(url, method, path, headers, body=b"{}"):
    """One request with exact headers; (status, parsed body or raw bytes)."""
    target = urlparse(url)
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
    try:
        connection.request(method, path, body=body if method == "POST" else None,
                           headers=headers)
        answer = connection.getresponse()
        raw = answer.read()
    finally:
        connection.close()
    try:
        return answer.status, json.loads(raw)
    except ValueError:
        return answer.status, raw


def test_ledger_entries_tell_two_keys_and_the_owner_apart(keyed, served):
    keys, _store = keyed
    first, _ = keys.create("ci-bot")
    second, _ = keys.create("teammate")
    url, _upstream, ledger = served(turn2(4))
    for path, credential in (("/v1/messages", first), ("/v1/responses", second),
                             ("/v1/messages", support.TOKEN), ("/v1/responses", first)):
        assert post(url, path, credential)[0] == 200
    said = [(entry.meta["interface"], entry.meta["key"], entry.meta.get("key_fp"))
            for entry in ledger.entries]
    one, two = keys.row("ci-bot")["fingerprint"], keys.row("teammate")["fingerprint"]
    assert one != two
    assert said == [("anthropic-messages", "ci-bot", one), ("openai-responses", "teammate", two),
                    ("anthropic-messages", "owner", None), ("openai-responses", "ci-bot", one)]
    assert "charged_tokens" not in ledger.entries[2].meta      # the owner has no budget
    assert all(entry.meta["usage_reported"] is True for entry in ledger.entries)
    assert keys.row("ci-bot")["totals"]["calls"] == 2
    assert keys.row("teammate")["totals"]["calls"] == 1
    assert ledger.verify()


@pytest.mark.parametrize("path", PATHS)
def test_a_revoked_key_and_an_unknown_key_get_401_and_reach_no_upstream(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served(turn2(1))
    assert post(url, path, raw)[0] == 200                       # control: it worked while live
    keys.revoke("ci-bot")
    never = "fwk_" + "never-minted-" * 3
    for offered in (raw, never, raw[:-2], "fwk_", raw + "\t"):
        status, _headers, body = post(url, path, offered)
        assert status == 401 and body == {"error": "unauthorized", "reason": "bad_token"}
    assert len(upstream.requests) == 1 and support.kinds(ledger) == ["endpoint_call"]


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/api/keychain/set", b'{"name": "bad\\u0001name"}'),
    ("POST", "/v1/chat/completions", b'{"model": "ollama", "messages": []}'),
    ("POST", "/api/keychain/delete", b'{"name": "bad\\u0001name"}'),
    ("GET", "/v1/models", b""),
])
def test_a_virtual_key_opens_no_route_but_the_model_interfaces(keyed, served, method, path, body):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, _ledger = served([])
    for header in ({"x-api-key": raw}, {"Authorization": f"Bearer {raw}"}):
        status, answer = _send(url, method, path,
                               {"Content-Type": "application/json", **header}, body)
        assert status == 401 and raw not in json.dumps(answer)
    owner, _answer = _send(url, method, path, {
        "Content-Type": "application/json", "Authorization": f"Bearer {support.TOKEN}"}, body)
    assert owner != 401                                         # control: the gateway token passes
    assert upstream.requests == []


@pytest.mark.parametrize("change, reason", [
    ({"Content-Type": "text/plain"}, "bad_token"),              # a CORS-simple body
    ({"Host": "evil.example"}, "bad_host"),                     # DNS rebinding
])
def test_a_virtual_key_still_needs_a_json_body_and_an_allowed_host(keyed, served, change, reason):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, _ledger = served(turn2(1))
    body = json.dumps(MESSAGES).encode()
    plain = {"Content-Type": "application/json", "x-api-key": raw}
    status, answer = _send(url, "POST", "/v1/messages", {**plain, **change}, body)
    assert status == 401 and answer["reason"] == reason and upstream.requests == []
    assert _send(url, "POST", "/v1/messages", plain, body)[0] == 200    # control


def test_a_get_on_an_interface_path_is_not_opened_by_a_virtual_key(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger = served([])
    status, answer = _send(url, "GET", "/v1/messages", {"x-api-key": raw})
    assert status == 401 and answer["reason"] == "bad_token"


@pytest.mark.parametrize("path, status, kind", [
    ("/v1/messages", 403, "permission_error"), ("/v1/responses", 403, "invalid_request_error")])
def test_a_model_off_the_allow_list_is_refused_with_nothing_sent_upstream(
        keyed, served, path, status, kind):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", models=["claude-haiku-4-5", "gpt-5.3-codex-spark"])
    url, upstream, ledger = served(turn2(1))
    got, _headers, body = post(url, path, raw)                  # the bodies name other models
    assert got == status and body["error"]["type"] == kind and upstream.requests == []
    named = BODIES[path]["model"]
    assert body["error"]["message"] == (
        f"gateway key 'ci-bot' may not use the model '{named}'; its allow-list is "
        "claude-haiku-4-5, gpt-5.3-codex-spark. Nothing was sent upstream.")
    if path == "/v1/responses":
        assert (body["error"]["code"], body["error"]["param"]) == ("model_not_allowed", "model")
    assert support.kinds(ledger) == ["endpoint_call_refused"]
    assert ledger.entries[0].meta["reason"] == "model_not_allowed"
    allowed = {**BODIES[path], "model": "claude-haiku-4-5"}
    assert post(url, path, raw, allowed)[0] == 200 and len(upstream.requests) == 1
    assert keys.row("ci-bot")["totals"]["calls"] == 1


def test_the_allow_list_binds_token_counting_too(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", models=["claude-haiku-4-5"])
    url, upstream, _ledger = served([])
    body = {"model": "claude-sonnet-5", "messages": [{"role": "user", "content": "Hi"}]}
    status, _headers, answer = post(url, "/v1/messages/count_tokens", raw, body)
    assert status == 403 and answer["error"]["type"] == "permission_error"
    assert upstream.requests == []


def test_with_gateway_authentication_off_a_key_is_still_itself(keyed, monkeypatch, tmp_path):
    """No gateway token: anyone is the owner, a live key is charged as that key,
    and a credential shaped like a key that is not live is refused by the interface."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    with support.Upstream(turn2(2)) as upstream, \
            support.gateway_server(monkeypatch, tmp_path, token="") as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        assert post(url, "/v1/messages", raw)[0] == 200
        assert post(url, "/v1/messages", "")[0] == 200
        keys.revoke("ci-bot")
        status, headers, body = post(url, "/v1/messages", raw)
        other, _headers, shaped = post(url, "/v1/responses", raw)
    assert [entry.meta["key"] for entry in ledger.entries] == ["ci-bot", "owner"]
    assert status == 401 and body["type"] == "error" and body["request_id"] == headers["request-id"]
    assert body["error"]["type"] == "authentication_error"
    assert other == 401 and shaped["error"]["code"] == "invalid_api_key"
    assert len(upstream.requests) == 2 and raw not in json.dumps([body, shaped])
