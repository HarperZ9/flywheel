#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.pack_privacy -- personal details before text leaves (rule pack `privacy`).

  private-email (MEDIUM)  an e-mail address. Reserved example domains
                          (example.com, .test, .invalid, .localhost) and
                          no-reply addresses are left alone.
  local-path (MEDIUM)     a path on one computer: a Windows drive path
                          (C:\\ or C:/), a home folder (/Users/name,
                          /home/name) or a network share (\\\\host\\share).
                          It names the machine's layout and often the
                          person's account name.

The pack reads the whole text, code blocks and inline code included, because
a path pasted into a code block leaves with the text just the same. The
`outbound` domain profile promotes both categories to the gate. The `note`,
`product-copy` and `publication` profiles report them without gating, since a
contact address there can be deliberate. Each pattern is closed: a path
written another way, or an address with its @ spelled out, is not caught.
Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util

NAME = "privacy"
CATEGORIES = ("private-email", "local-path")
OPTIONS = {}

_EMAIL = re.compile(r"(?<![\w.%+-])([\w.%+-]{1,64})@((?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24})\b")
_RESERVED = re.compile(r"(?i)(?:^|\.)(?:example\.(?:com|org|net)|example|test|invalid|localhost)$")
_NOREPLY = re.compile(r"(?i)^(?:no-?reply|do-?not-?reply)$|(?:^|\.)users\.noreply\.github\.com$")
_PATH = re.compile(
    r"(?<![\w/\\])[A-Za-z]:[\\/](?:[^\s`'\"<>|)\]]+)?"          # C:\dev or C:/dev
    r"|(?<![\w.~])/(?:Users|home)/[A-Za-z0-9._-]+[^\s`'\"<>)\]]*"  # /Users/name, /home/name
    r"|(?<![\w\\])\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9.$_-]+")          # \\host\share


def _lines(text):
    off = 0
    for i, raw in enumerate(text.splitlines(keepends=True), 1):
        yield i, off, raw
        off += len(raw)


def _emails(raw):
    for m in _EMAIL.finditer(raw):
        local, domain = m.group(1), m.group(2)
        if _RESERVED.search(domain) or _NOREPLY.search(local) or _NOREPLY.search(domain):
            continue
        yield m


def scan(text, prose, opts, make):
    found = pack_util.empty()
    for line_no, off, raw in _lines(text):
        snippet = raw.strip()[:100]
        for m in _emails(raw):
            found["MEDIUM"].append(make(
                line_no, off, "private-email",
                "e-mail address; remove it or confirm it may leave with the text",
                m.start(), m.end(), raw, snippet))
        for m in _PATH.finditer(raw):
            found["MEDIUM"].append(make(
                line_no, off, "local-path",
                "path on this computer; it names the machine and often the account",
                m.start(), m.end(), raw, snippet))
    return found


def fingerprint():
    return [_EMAIL.pattern, _RESERVED.pattern, _NOREPLY.pattern, _PATH.pattern]
