"""endpoints_sse.py -- open a provider's event stream and read its events.

Hosted providers stream a reply as server-sent events: lines of `event: NAME`
and `data: JSON`, with a blank line after each event. Two things live here.

  open_stream  the injectable transport for a streamed request. It returns
               (status, lines) for a 200, where `lines` yields the body one
               line at a time as the bytes arrive, and (status, error object)
               for anything else, read the way endpoints_http reads a fault.
  events       turns those lines into (event name, parsed data) pairs.

A test swaps `open_stream` for a function that replays a recorded stream, so
no test needs a network.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import endpoints_http
from .provider_fault_boundary import body_from_http_error

DONE = "[DONE]"            # OpenAI's last data line; it is not JSON


def open_stream(method, url, headers, body, timeout):
    """(method,url,headers,body,timeout) -> (status, lines or error object)."""
    endpoints_http._FAULT.last = None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        obj = body_from_http_error(e)
        endpoints_http._FAULT.last = (obj, endpoints_http._header_map(getattr(e, "headers", None)))
        return e.code, obj
    if resp.status != 200:
        try:
            raw = resp.read(65536)
        finally:
            resp.close()
        try:
            return resp.status, json.loads(raw) if raw else {}
        except ValueError:
            return resp.status, {"error": raw.decode("utf-8", "replace")[:200]}
    return resp.status, resp


def _text(line) -> str:
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    return line.rstrip("\r\n")


def _data(lines: list):
    """The joined data lines of one event, parsed. DONE passes through as text."""
    joined = "\n".join(lines)
    return DONE if joined.strip() == DONE else json.loads(joined)


def events(lines):
    """Yield (event name, data) for each event in an SSE body.

    Follows the event stream format: `event:` names the event, `data:` lines
    are joined with a newline, a line that starts with `:` is a comment, and a
    blank line ends the event. An event with no data is skipped. Data that is
    not JSON raises ValueError, which the caller reports as a broken stream.
    """
    name, data = "", []
    for raw in lines:
        line = _text(raw)
        if not line:
            if data:
                yield name, _data(data)
            name, data = "", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            name = value
        elif field == "data":
            data.append(value)
    if data:                     # a body that ends without the last blank line
        yield name, _data(data)
