#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""corpus.py - EMET marker corpus loader and matcher (shared core).

The marker denylist is a versioned, sha-pinned DATA artifact (SPEC sections 8 and
16), loaded identically by membrane.py (refuse) and monitor.py (census). Matching
is literal ASCII-case-insensitive substring over RAW BYTES - no regex - so an
independent implementation re-derives identical counts. The byte-hash core does
NOT depend on this module (SPEC section 8).
"""
import os, hashlib

DEFAULT_NAME = "markers.corpus"
REPL = b"[REFUSED-IN-BAND-AUTHORITY]"

class CorpusError(Exception):
    """Inability to load the corpus; .reason is a stable machine code."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

def corpus_path():
    # Resolution (SPEC s.8): EMET_CORPUS wins; otherwise the versioned corpus that
    # ships with the source. This module lives in the emet/ package, so the corpus
    # is one level up at <repo>/conformance/markers.corpus (NOT emet/conformance).
    # An installed wheel does not bundle the corpus, so refuse/monitor there report
    # UNVERIFIABLE reason=E_NO_CORPUS unless EMET_CORPUS is set (never a silent empty
    # denylist) - run from a checkout, or point EMET_CORPUS at the corpus.
    env = os.environ.get("EMET_CORPUS")
    if env:
        return env
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(pkg_parent, "conformance", DEFAULT_NAME)

def load():
    """Return (version:int, sha256_hex:str, markers:list[bytes] lowercased).
    Raise CorpusError('E_NO_CORPUS') if unreadable, ('E_NO_CORPUS_VERSION') if the
    header is absent."""
    path = corpus_path()
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        raise CorpusError("E_NO_CORPUS")
    sha = hashlib.sha256(data).hexdigest()
    version = None
    markers = []
    for line in data.split(b"\n"):
        if line.endswith(b"\r"):
            line = line[:-1]
        if line[:1] == b"#":
            meta = line[1:].strip()
            if version is None and meta[:15].lower() == b"corpus_version:":
                try:
                    version = int(meta[15:].strip())
                except ValueError:
                    pass
            continue
        if line.strip() == b"":
            continue
        markers.append(line.lower())  # bytes.lower() is ASCII-only
    if version is None:
        raise CorpusError("E_NO_CORPUS_VERSION")
    return version, sha, markers

def _alower(b):
    return b + 32 if 65 <= b <= 90 else b

def matches_at(hay, i, m):
    if i + len(m) > len(hay):
        return False
    for j in range(len(m)):
        if _alower(hay[i + j]) != m[j]:
            return False
    return True

def scan(hay, markers):
    """Non-overlapping leftmost scan in corpus order.
    Return (hits, redacted_bytes) where hits is a list of (offset, length)."""
    out = bytearray()
    hits = []
    i = 0
    n = len(hay)
    while i < n:
        ln = 0
        for m in markers:
            if m and matches_at(hay, i, m):
                ln = len(m)
                break
        if ln:
            hits.append((i, ln))
            out += REPL
            i += ln
        else:
            out.append(hay[i])
            i += 1
    return hits, bytes(out)

def count(hay, markers):
    return len(scan(hay, markers)[0])
