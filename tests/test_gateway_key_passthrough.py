"""Pass-through controls on a virtual key, in front of an Anthropic upstream.

A Messages request to an Anthropic upstream is forwarded as sent, so its
fields decide what the provider account is billed for. A virtual key may
forward an `anthropic-beta` value, a provider-defined tool or `mcp_servers`
only when its allow-list names it. A new key allows none. The gateway token
forwards everything.

A real gateway on a loopback port, a stub upstream, keys in the in-memory
store. No provider is called.
"""
import json

import pytest

from tests import gateway_messages_support as support
from tests.gateway_keys_support import MESSAGES, keyed, served  # noqa: F401  (fixtures)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

WEB_SEARCH = [{"type": "web_search_20250305", "name": "web_search"}]
CUSTOM = [{"name": "read", "description": "Read a file.",
           "input_schema": {"type": "object", "properties": {}}}]


def _anthropic(keyed, served, **policy):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    if policy:
        keys.mark("ci-bot", **policy)
    plain = support.load("upstream/anthropic_cached.json")
    url, upstream, ledger = served([support.json_answer(plain)] * 2, provider="anthropic")
    return keys, raw, url, upstream, ledger


def _post_beta(url, raw, body, beta=None):
    import urllib.error
    import urllib.request
    headers = {"Content-Type": "application/json", "x-api-key": raw}
    if beta:
        headers["anthropic-beta"] = beta
    request = urllib.request.Request(url + "/v1/messages", data=json.dumps(body).encode(),
                                     method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.mark.parametrize("body, beta, field", [
    ({**MESSAGES, "tools": WEB_SEARCH}, None, "tools.0.type"),
    ({**MESSAGES, "tools": CUSTOM + WEB_SEARCH}, None, "tools.1.type"),
    ({**MESSAGES, "mcp_servers": [{"type": "url", "url": "https://example.com/mcp",
                                   "name": "x"}]}, None, "mcp_servers"),
    (MESSAGES, "code-execution-2025-08-25", "anthropic-beta"),
    (MESSAGES, "allowed-one,not-allowed-one", "anthropic-beta"),
])
def test_a_key_without_the_allowance_is_refused_and_nothing_goes_upstream(
        keyed, served, body, beta, field):
    _keys, raw, url, upstream, ledger = _anthropic(keyed, served, betas=["allowed-one"])
    status, answer = _post_beta(url, raw, body, beta)
    assert status == 403 and answer["error"]["type"] == "permission_error"
    assert field in answer["error"]["message"]
    assert "gateway-key set ci-bot" in answer["error"]["message"]
    assert upstream.requests == []
    assert [(e.kind, e.meta["reason"]) for e in support.recorded(ledger)] == [
        ("endpoint_call_refused", "field_not_allowed")]


def test_a_key_with_the_allowances_passes_them_through(keyed, served):
    _keys, raw, url, upstream, _ledger = _anthropic(
        keyed, served, betas=["allowed-one"], server_tools=["web_search"], mcp=True)
    body = {**MESSAGES, "tools": CUSTOM + WEB_SEARCH, "mcp_servers": []}
    assert _post_beta(url, raw, body, "allowed-one")[0] == 200
    sent = upstream.requests[0]
    assert sent["headers"]["anthropic-beta"] == "allowed-one"
    assert sent["body"]["tools"] == CUSTOM + WEB_SEARCH


def test_control_custom_tools_need_no_allowance_and_the_owner_passes_everything(
        keyed, served):
    _keys, raw, url, upstream, _ledger = _anthropic(keyed, served)
    assert _post_beta(url, raw, {**MESSAGES, "tools": CUSTOM})[0] == 200
    status, _answer = _post_beta(url, support.TOKEN, {**MESSAGES, "tools": WEB_SEARCH},
                                 "code-execution-2025-08-25")
    assert status == 200 and len(upstream.requests) == 2
    assert upstream.requests[1]["headers"]["anthropic-beta"] == "code-execution-2025-08-25"
