"""payload.py -- the model-API payload predicate behind rule egress/003.

egress/002 holds a call that names an off-allowlist host as a literal
`scheme://host` token. A model-API request can make the provider fetch a
URL for the agent, and three forms of that hide the host from egress/002
(experiment N1): the body base64-encoded in the shell, the body written to a
script file by one call and run by the next, and a server-side search or
fetch tool enabled with no URL at all.

This predicate reads the inspected text (an exec command, a write's
content, or an MCP call's arguments) and fires when it carries:

- a server-side fetch or search tool type (web_search*, web_fetch*,
  google_search), or
- a URL-typed input key (file_url, image_url, fileUri, file_uri,
  document_url, input_file, or a source of type "url") whose http(s) host is
  off the allowlist, or whose value is a shell or template variable rather
  than a literal URL.

One level of base64 decoding is applied first. Pure: same text and hosts,
same answer.

Does not prove intent. It does not catch a body split so that no decodable
URL-typed key survives in any single inspected call, and two levels of
encoding pass. The complete control for a determined agent is at the egress
proxy, which sees the decoded body on the wire.
"""
from __future__ import annotations

import base64
import binascii
import re

_TOOLTYPE = re.compile(
    r'"type\\?"\s*:\s*\\?"(web_search\w*|web_fetch\w*)\\?"|"google_search\\?"\s*:', re.IGNORECASE)
_URLKEY = re.compile(
    r'"?\b(file_url|image_url|fileUri|file_uri|document_url|input_file)\b\\?"?\s*[:=]'
    r'|"type\\?"\s*:\s*\\?"url\\?"', re.IGNORECASE)
_URL_HOST = re.compile(r"https?://([A-Za-z0-9._-]+)", re.IGNORECASE)
# A URL-typed key whose quoted value starts with a shell or template variable.
_VAR_VALUE = re.compile(
    r'\b(file_url|image_url|fileUri|file_uri|document_url|input_file|url)\b\\?"?\s*:\s*\\?"\s*[$%{]',
    re.IGNORECASE)
_B64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


def _scan(text: str, allowed: set) -> str:
    if _TOOLTYPE.search(text):
        return "enables a server-side fetch or search tool"
    if not _URLKEY.search(text):
        return ""
    off = sorted({h.lower() for h in _URL_HOST.findall(text)} - allowed)
    if off:
        return "URL-typed input to off-allowlist host " + ", ".join(off)
    if _VAR_VALUE.search(text):
        return "URL-typed input built from a variable, not a literal URL"
    return ""


def model_api_url_payload(text: str, allowed: set) -> str:
    """Return a short reason when `text` carries a disguised model-API fetch,
    else "". `allowed` holds lower-case host names."""
    if not text:
        return ""
    reason = _scan(text, allowed)
    if reason:
        return reason
    for blob in _B64.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4)).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            continue
        reason = _scan(decoded, allowed)
        if reason:
            return "base64: " + reason
    return ""
