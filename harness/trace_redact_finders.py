"""Validators and line-based finders for the redaction catalog.

A validator rejects a candidate that has a rule's shape but not its
structure: a card number that fails Luhn, an IBAN that fails mod 97, a JWT
whose header is not JSON. A finder locates a multi-line block or a
context-dependent value with plain string searches, so its cost stays linear
where one regular expression over the block would not.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
from typing import Iterator

_STRIP = str.maketrans("", "", " -")
_DOUBLE = (0, 2, 4, 6, 8, 1, 3, 5, 7, 9)
_IBAN_DIGITS = str.maketrans({chr(c): str(c - 55) for c in range(65, 91)})
_HEX = frozenset("0123456789abcdefABCDEF")
_BEARER_SIGNAL = frozenset("0123456789._~+/=-")


def luhn_valid(text: str) -> bool:
    digits = text.translate(_STRIP)
    if not (13 <= len(digits) <= 19 and digits.isdigit()):
        return False
    odd = sum(map(int, digits[-1::-2]))
    even = sum(_DOUBLE[int(c)] for c in digits[-2::-2])
    return (odd + even) % 10 == 0


def iban_valid(text: str) -> bool:
    compact = text.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    numeric = (compact[4:] + compact[:4]).translate(_IBAN_DIGITS)
    return numeric.isdigit() and int(numeric) % 97 == 1


def jwt_header_valid(text: str) -> bool:
    header = text.split(".", 1)[0]
    if len(header) > 4096:
        return False
    try:
        decoded = base64.urlsafe_b64decode(header + "=" * (-len(header) % 4))
        value = json.loads(decoded)
    except (ValueError, binascii.Error, UnicodeDecodeError, RecursionError):
        return False
    return type(value) is dict and type(value.get("alg")) is str


def bearer_value(value: str) -> bool:
    return len(value) >= 16 and any(c in _BEARER_SIGNAL for c in value)


def basic_value(value: str) -> bool:
    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False
    return ":" in decoded and decoded.isprintable()


def userinfo_value(value: str) -> bool:
    return ":" in value or len(value) >= 16


def cookie_value(value: str) -> bool:
    return "=" in value


def ipv6_valid(value: str) -> bool:
    if sum(c in _HEX for c in value) < 3:
        return False
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return True


_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----")
_END = re.compile(r"-----END [A-Z0-9 ]{0,40}PRIVATE KEY-----")


def pem_blocks(text: str) -> Iterator[tuple[int, int]]:
    """BEGIN ... PRIVATE KEY through its END line; an unterminated block runs
    to the end of the text, since a cut block still leaks key material."""
    pos = 0
    while True:
        opened = _BEGIN.search(text, pos)
        if opened is None:
            return
        start = opened.start()
        probe = text.find("-----END ", opened.end())
        while probe >= 0:
            closed = _END.match(text, probe)
            if closed is not None:
                yield start, closed.end()
                pos = closed.end()
                break
            probe = text.find("-----END ", probe + 9)
        else:
            yield start, len(text)
            return


def putty_blocks(text: str) -> Iterator[tuple[int, int]]:
    """A PuTTY key file from its first line through the Private-MAC line."""
    pos = 0
    while True:
        start = text.find("PuTTY-User-Key-File-", pos)
        if start < 0:
            return
        mac = text.find("Private-MAC:", start)
        if mac < 0:
            yield start, len(text)
            return
        newline = text.find("\n", mac)
        end = len(text) if newline < 0 else newline
        yield start, end
        pos = end


_URL = re.compile(r"(?i)https?://[^\s\"'<>]{1,8192}+")
_CODE = re.compile(r"[?&]code=([^&#\s\"'<>]{1,4096}+)")
_STATE = re.compile(r"[?&]state=")
_OAUTH_PATH = re.compile(r"(?i)oauth|callback|authori[sz]e")


def oauth_codes(text: str) -> Iterator[tuple[int, int]]:
    """A code parameter is an authorization code only in an OAuth-shaped URL:
    one that also carries state, or whose path names the flow. A bare code=
    is common in ordinary URLs and is kept."""
    for url in _URL.finditer(text):
        found = _CODE.search(url.group(0))
        if found is None:
            continue
        path = url.group(0).split("?", 1)[0]
        if _STATE.search(url.group(0)) or _OAUTH_PATH.search(path):
            yield url.start() + found.start(1), url.start() + found.end(1)
