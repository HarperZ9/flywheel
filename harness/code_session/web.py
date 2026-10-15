"""web.py -- the session's `web_fetch` tool.

Fetches one URL over HTTPS (plain HTTP only for loopback), reads at most
MAX_BYTES, turns HTML into text, and returns it with the response's status,
content type, byte count and sha256, so the ledger says exactly what came
back. Fetching is a network call: the permission mode treats it like a command
(ask in ask and edit, run in auto, refused in plan), and permission rules match
against the URL, as in `"web_fetch:https://docs.python.org/*"`.
"""
from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import urllib.request

MAX_BYTES = 512 * 1024
MAX_TEXT = 20000
TIMEOUT = 20
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def check_url(url: str) -> "str | None":
    """A refusal reason, or None when the URL may be fetched."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return None
    if parts.scheme == "http" and (parts.hostname or "") in _LOOPBACK:
        return None
    return "only https URLs (or http on loopback) are fetched"


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch(url: str, *, opener=urllib.request.urlopen) -> "tuple[bool, str]":
    refused = check_url(url)
    if refused:
        return False, f"[refused] {refused}: {url}"
    req = urllib.request.Request(url, headers={"User-Agent": "flywheel-code (web_fetch)"})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            status = getattr(resp, "status", 200)
            ctype = resp.headers.get("Content-Type", "") if resp.headers else ""
            body = resp.read(MAX_BYTES + 1)
    except Exception as e:                         # a fetch failure is a result, not a crash
        return False, f"[error] fetch failed: {e.__class__.__name__}: {e}"[:400]
    truncated = len(body) > MAX_BYTES
    body = body[:MAX_BYTES]
    text = body.decode("utf-8", errors="replace")
    if "html" in ctype.lower() or text.lstrip().lower().startswith(("<!doctype", "<html")):
        text = html_to_text(text)
    head = (f"[{status} {ctype or 'unknown type'} | {len(body)} bytes"
            f"{' (truncated)' if truncated else ''} | sha256 {hashlib.sha256(body).hexdigest()}]")
    return 200 <= status < 400, head + "\n" + text[:MAX_TEXT]
