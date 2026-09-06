"""content_length.py -- the header block two protocols in this tree share.

LSP and DAP both carry their messages the same way: an ASCII header block, a
blank line, then exactly that many bytes of UTF-8 JSON. Neither protocol
invented it and neither owns it, so the delimiting rules live here and the two
wire modules keep only what is theirs, which is what a message means.

Written from the specifications rather than lifted from a client library. If
this file and a real server disagree about where a message ends, the
disagreement should surface as a failure rather than as two copies of one
mistake.

A header this side cannot parse ends the connection instead of being answered.
After a bad length nobody knows where the next message starts, and reading on
from there would invent messages the far side never sent.
"""
from __future__ import annotations

import json
from typing import BinaryIO

from .jsonrpc import WireError

CONTENT_LENGTH = "content-length"
CONTENT_TYPE = "content-type"

# A ceiling on one message, so a peer that reports a length it will never send
# fails here with a name instead of blocking the reader thread forever. Well
# above any real message: the largest thing that crosses is a document open
# carrying a whole file, and 64 MiB of JSON-escaped source is not a file anyone
# edits.
MAX_CONTENT_LENGTH = 64 * 1024 * 1024

__all__ = ["CONTENT_LENGTH", "CONTENT_TYPE", "MAX_CONTENT_LENGTH",
           "content_length", "encode", "read_body", "read_headers"]


def encode(message: dict) -> bytes:
    """Serialize one message with the header block that delimits it.

    The length counts bytes and not characters. Getting that wrong is the
    classic bug in both protocols, and it only shows up once a message carries a
    character outside ASCII, so the length is taken from the encoded body and
    never from the string.
    """
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_headers(stream: BinaryIO) -> dict[str, str] | None:
    """Read one header block. None once the stream has ended cleanly.

    Field names are lowercased on the way in. Both specifications write
    Content-Length with that capitalization and every implementation sends it
    that way, but a case-sensitive reader would fail on a legal variation for no
    reason.
    """
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            if headers:
                raise WireError("the stream ended inside a header block")
            return None
        if line in (b"\r\n", b"\n"):
            return headers
        try:
            text = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise WireError(f"a header is ASCII: {exc}") from exc
        name, separator, value = text.partition(":")
        if not separator:
            raise WireError(f"a header is name: value, got {text.strip()!r}")
        headers[name.strip().lower()] = value.strip()


def content_length(headers: dict[str, str]) -> int:
    """The declared body length, or say which rule the header block broke."""
    raw = headers.get(CONTENT_LENGTH)
    if raw is None:
        raise WireError("a message carries a Content-Length header")
    try:
        length = int(raw)
    except ValueError as exc:
        raise WireError(f"Content-Length is an integer, got {raw!r}") from exc
    if length < 0:
        raise WireError(f"Content-Length is not negative, got {length}")
    if length > MAX_CONTENT_LENGTH:
        raise WireError(f"Content-Length {length} is over the "
                        f"{MAX_CONTENT_LENGTH} byte ceiling")
    _check_charset(headers.get(CONTENT_TYPE))
    return length


def _check_charset(content_type: str | None) -> None:
    """UTF-8 or nothing. utf8 is the deprecated spelling and is still accepted.

    A peer that declares another charset is not one this client can read, and
    guessing would put mojibake into a chain that claims to hold what crossed.
    """
    if not content_type:
        return
    for part in content_type.split(";")[1:]:
        name, separator, value = part.partition("=")
        if separator and name.strip().lower() == "charset":
            charset = value.strip().strip('"').lower()
            if charset not in ("utf-8", "utf8"):
                raise WireError(f"the body is UTF-8, not {charset!r}")


def read_body(stream: BinaryIO, length: int) -> bytes:
    """Read exactly `length` bytes, or say the message was cut short.

    One read is not enough: a pipe hands back what has arrived rather than what
    was asked for, and the short read is where a client that works on one
    machine starts dropping messages on a slower one.
    """
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise WireError(f"the stream ended {remaining} bytes into a "
                            f"{length} byte message")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
