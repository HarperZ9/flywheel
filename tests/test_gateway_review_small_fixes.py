"""Smaller findings of the 2.0 security review, each with its control.

  deep JSON nesting      400 in the interface's error shape, not 500
  non-ASCII credential   401, not a dropped connection
  revoke                 fails loudly when the credential store keeps the key
  key list file          owner-only on POSIX
  redaction              a gateway key in free text is scrubbed
  redirects              an upstream redirect is not followed, so the provider
                         key header is not re-sent to another host
  x_receipt, x_flywheel  an upstream cannot put these on a relayed event

A real gateway on a loopback port with stub upstreams. No provider is called.
"""
import http.client
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from harness import endpoints_http, endpoints_sse, gateway_key_cli, gateway_keys
from harness.provider_fault_boundary import redacted_text
from tests import gateway_messages_support as support
from tests.gateway_keys_support import MESSAGES, keyed, post, served  # noqa: F401

PATHS = ["/v1/messages", "/v1/responses"]


def _raw_post(url, path, headers: dict, body: bytes):
    target = urlparse(url)
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=30)
    try:
        connection.putrequest("POST", path)
        for name, value in {"Content-Type": "application/json",
                            "Content-Length": str(len(body)), **headers}.items():
            connection.putheader(name, value)
        connection.endheaders()
        connection.send(body)
        answer = connection.getresponse()
        return answer.status, answer.read()
    finally:
        connection.close()


@pytest.mark.parametrize("path", PATHS)
def test_deeply_nested_json_is_a_bad_request(served, path):
    url, upstream, ledger = served([])
    deep = b'{"model":"m","max_tokens":1,"messages":' + b"[" * 100000 + b"]" * 100000 + b"}"
    status, body = _raw_post(url, path, {"x-api-key": support.TOKEN}, deep)
    assert status == 400 and json.loads(body)["error"]["type"] == "invalid_request_error"
    assert upstream.requests == [] and ledger.entries == []


@pytest.mark.parametrize("path", ["/v1/messages", "/v1/models"])
@pytest.mark.parametrize("header", ["x-api-key", "Authorization"])
def test_a_non_ascii_credential_gets_401(served, path, header):
    url, upstream, _ledger = served([])
    value = "caf\xe9" if header == "x-api-key" else "Bearer caf\xe9"
    status, body = _raw_post(url, path, {header: value.encode("latin-1")}, b"{}")
    assert status == 401 and json.loads(body)["reason"] == "bad_token"
    assert upstream.requests == []


def test_control_the_right_token_still_opens_the_route(served):
    url, _upstream, _ledger = served([])
    status, _body = _raw_post(url, "/v1/messages", {"x-api-key": support.TOKEN}, b"{}")
    assert status == 400, "authenticated, then refused for its empty body"


def test_revoke_fails_when_the_store_keeps_the_key(keyed, capsys):
    keys, store = keyed
    raw, _ = keys.create("ci-bot")
    store.delete = lambda name: {"error": "the credential store is locked"}
    with pytest.raises(gateway_keys.KeysError, match="did not delete the stored key"):
        keys.revoke("ci-bot")
    assert keys.row("ci-bot")["revoked"] is True, "the flag still blocks the key"
    assert keys.authenticate(raw)[1]["revoked"] is True
    code = gateway_key_cli.main(["revoke", "ci-bot"], store=store,
                                environ={"FLYWHEEL_HOME": str(keys.path.parent)})
    assert code == 1 and "did not delete the stored key" in capsys.readouterr().err


def test_control_revoke_succeeds_when_the_store_deletes_the_key(keyed):
    keys, store = keyed
    keys.create("ci-bot")
    assert keys.revoke("ci-bot")["revoked"] is True and store.saved == {}
    assert keys.revoke("ci-bot")["revoked"] is True, "revoking twice is not an error"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_the_key_list_is_owner_only_on_posix(keyed):
    keys, _store = keyed
    keys.create("ci-bot")
    assert keys.path.stat().st_mode & 0o777 == 0o600


def test_a_gateway_key_in_free_text_is_redacted(keyed):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    shown = redacted_text(f"upstream echoed x-api-key: {raw} in its error")
    assert raw not in shown and raw[4:] not in shown
    assert "upstream echoed" in shown, "control: the rest of the text is kept"


class _Hosts:
    """Two loopback hosts. The first answers every POST with a redirect to the second."""

    def __init__(self, code: int):
        self.second_saw, hosts = [], self

        class Second(BaseHTTPRequestHandler):
            def do_POST(self):
                hosts.second_saw.append({k.lower(): v for k, v in self.headers.items()})
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
            do_GET = do_POST

            def log_message(self, *args):
                pass
        self.second = ThreadingHTTPServer(("127.0.0.1", 0), Second)
        target = f"http://127.0.0.1:{self.second.server_address[1]}/elsewhere"

        class First(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(code)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass
        self.first = ThreadingHTTPServer(("127.0.0.1", 0), First)
        self.url = f"http://127.0.0.1:{self.first.server_address[1]}/v1/messages"
        for server in (self.first, self.second):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def close(self):
        for server in (self.first, self.second):
            server.shutdown()
            server.server_close()


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_an_upstream_redirect_is_not_followed(code):
    hosts = _Hosts(code)
    headers = {"x-api-key": "test-provider-key-not-real", "Content-Type": "application/json"}
    try:
        status, _obj = endpoints_http._http("POST", hosts.url, headers, b"{}", 10)
        opened, _lines = endpoints_sse.open_stream("POST", hosts.url, headers, b"{}", 10)
    finally:
        hosts.close()
    assert (status, opened) == (code, code), "the redirect is the answer"
    assert hosts.second_saw == [], "the second host received no request and no key"


def test_control_the_stock_opener_follows_the_redirect_with_the_key():
    """What the transports did before: urllib re-sends the headers to the new host."""
    import urllib.request
    hosts = _Hosts(302)
    request = urllib.request.Request(hosts.url, data=b"{}", method="POST",
                                     headers={"x-api-key": "test-provider-key-not-real"})
    try:
        urllib.request.urlopen(request, timeout=10).read()
    finally:
        hosts.close()
    assert [seen.get("x-api-key") for seen in hosts.second_saw] == ["test-provider-key-not-real"]


def _event(name: str, data: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


def test_an_upstream_cannot_put_the_gateways_fields_on_a_relayed_event(served):
    start = {"type": "message_start", "x_receipt": {"receipt_id": "FORGED-ONE"},
             "x_flywheel": {"usage_reported": "FORGED-TWO"},
             "message": {"id": "msg_fixture", "type": "message", "role": "assistant",
                         "model": "claude-sonnet-5", "content": [], "stop_reason": None,
                         "stop_sequence": None,
                         "usage": {"input_tokens": 3, "output_tokens": 1}}}
    block = _event("content_block_start", {"type": "content_block_start", "index": 0,
                                           "content_block": {"type": "text", "text": ""}})
    rest = block + b"".join([
        _event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                       "delta": {"type": "text_delta", "text": "hi"}}),
        _event("content_block_stop", {"type": "content_block_stop", "index": 0}),
        _event("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                                 "usage": {"output_tokens": 2}}),
        _event("message_stop", {"type": "message_stop",
                                "x_receipt": {"receipt_id": "FORGED-THREE"}})])
    url, _upstream, ledger = served([support.stream_answer(_event("message_start", start) + rest)],
                                    provider="anthropic")
    status, _headers, body = post(url, "/v1/messages", support.TOKEN,
                                  {**MESSAGES, "stream": True})
    assert status == 200 and b"FORGED" not in body
    events = support.events(body)
    assert events[0][0] == "message_start" and events[0][1]["message"] == start["message"]
    assert block in body, "control: an event without those fields is relayed byte for byte"
    assert [name for name, data in events if "x_receipt" in data] == ["message_stop"]
    assert support.kinds(ledger) == ["endpoint_call"]
