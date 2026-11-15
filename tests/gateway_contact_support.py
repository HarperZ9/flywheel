"""Helpers shared by the two files that test accounting at upstream contact.

  tests/test_gateway_contact_accounting.py   R1 and the request the gateway cannot hash
  tests/test_gateway_contact_invariant.py    the invariant by fault injection
"""
import json
import urllib.error
import urllib.request

from tests.gateway_keys_support import BODIES

PATHS = ["/v1/messages", "/v1/responses"]
PROVIDERS = ["openai", "anthropic"]
ESCAPE = chr(92) + "ud800"              # the six characters \ud800, never a raw surrogate


def raw_post(url: str, path: str, key: str, body: bytes) -> tuple:
    """POST bytes as they are; (status, body bytes)."""
    request = urllib.request.Request(
        url + path, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def sent(path: str, stream: bool) -> bytes:
    return json.dumps({**BODIES[path], "stream": stream}).encode()


def unhashable(path: str, stream: bool) -> bytes:
    """The request body of `path` with a lone surrogate escape in the user's text."""
    body = sent(path, stream).decode()
    assert '"What changed?"' in body
    return body.replace('"What changed?"', '"What changed? ' + ESCAPE + '"').encode()


def calls(ledger) -> list:
    return [e for e in ledger.entries if e.kind in ("endpoint_call", "endpoint_call_failed")]
