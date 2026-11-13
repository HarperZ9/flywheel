"""key_check.py -- ask a provider whether a key works, before it is stored.

One GET per check, to the cheapest authenticated route the provider documents:
a models list, or OpenRouter's key-information route because its models list
answers without a key. No completion is requested and no tokens are spent. The
key travels in a header and never in the URL. Redirects are refused, so a key
is sent to the provider's own host and nowhere else.

The answer is one line: "the key works", or the provider's own reason read
through the fault reader and scrubbed of anything shaped like a credential.
The transport is a parameter, so tests answer for the provider and never open
a socket.
"""
from __future__ import annotations

import urllib.error
import urllib.request

from harness import provider_fault_boundary

TIMEOUT_SECONDS = 15


def _bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def _anthropic(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": "2023-06-01"}


def _gemini(key: str) -> dict:
    return {"x-goog-api-key": key}


# provider -> (URL, header builder). Every route is a read with no model call.
ROUTES = {
    "anthropic": ("https://api.anthropic.com/v1/models", _anthropic),
    "openai": ("https://api.openai.com/v1/models", _bearer),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", _gemini),
    "deepseek": ("https://api.deepseek.com/v1/models", _bearer),
    "openrouter": ("https://openrouter.ai/api/v1/key", _bearer),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None     # the 3xx surfaces as an HTTPError; the key is not re-sent


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(url: str, headers: dict, timeout: float) -> tuple:
    """(status, headers, body) for one GET. An HTTP error status is an answer,
    not an exception; a connection failure raises to the caller."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), {}
    except urllib.error.HTTPError as error:
        return (error.code, dict((error.headers or {}).items()),
                provider_fault_boundary.body_from_http_error(error))


def _without(text: str, key: str) -> str:
    """The pattern scrubber has already run; this removes the exact key too,
    for a key whose shape no pattern knows."""
    return text.replace(key, "[key removed]") if key else text


def check_key(provider: str, key: str, transport=None,
              timeout: float = TIMEOUT_SECONDS) -> "tuple[bool | None, str]":
    """(True, line) when the provider accepted the key, (False, line) with the
    provider's reason when it did not, (None, line) when it gave no answer."""
    if provider not in ROUTES:
        return None, f"no key test is defined for {provider}"
    url, build_headers = ROUTES[provider]
    send = transport or urllib_transport
    try:
        status, headers, body = send(url, build_headers(key), timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, (f"could not reach {provider} to test the key "
                      f"({type(exc).__name__}); no answer, so the key is untested")
    if isinstance(status, int) and 200 <= status < 300:
        return True, f"the key works ({provider} accepted it)"
    line = provider_fault_boundary.format_provider_fault(
        provider, status, body, headers=headers, kind=provider)
    return False, _without(f"the key was not accepted: {line}", key)
