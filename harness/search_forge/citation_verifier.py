# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""N43 Uncheatable Search-Forge Byte-Offset Citation Span Provenance Verifier.

Verifies that every cited quote matches an exact UTF-8 byte slice inside an
out-of-band source corpus identified by its FIPS 180-4 SHA-256 digest.
Hallucinated quotes, shifted byte offsets, out-of-bounds spans, and mismatched
source digests fail closed. Pure Python standard library only.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


def sha256_bytes(data: bytes) -> str:
    """Return canonical sha256:<64-hex> digest of raw bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CitationSpan:
    """Immutable byte-offset citation record tied to an exact source digest."""

    source_id: str
    source_sha256: str
    byte_start: int
    byte_end: int
    quoted_text: str
    span_sha256: str


@dataclass(frozen=True)
class CitationVerdict:
    """Fail-closed verification verdict for one CitationSpan."""

    ok: bool
    verdict: str
    reason: str
    source_id: str
    computed_span_sha256: str


def seal_citation_span(
    source_id: str,
    corpus_bytes: bytes,
    byte_start: int,
    byte_end: int,
) -> CitationSpan:
    """Create a sealed CitationSpan directly from raw source bytes."""
    if not source_id.strip():
        raise ValueError("source_id must be non-empty")
    if byte_start < 0 or byte_end <= byte_start or byte_end > len(corpus_bytes):
        raise ValueError(f"invalid byte span [{byte_start}, {byte_end}) for length {len(corpus_bytes)}")
    raw_slice = corpus_bytes[byte_start:byte_end]
    quoted_text = raw_slice.decode("utf-8")
    return CitationSpan(
        source_id=source_id.strip(),
        source_sha256=sha256_bytes(corpus_bytes),
        byte_start=byte_start,
        byte_end=byte_end,
        quoted_text=quoted_text,
        span_sha256=sha256_bytes(raw_slice),
    )


def verify_citation_span(
    span: CitationSpan,
    corpus_store: dict[str, bytes],
) -> CitationVerdict:
    """Independently re-verify a citation span against out-of-band source bytes."""
    if span.source_id not in corpus_store:
        return CitationVerdict(False, "REJECT", "missing_source_id", span.source_id, "")
    raw = corpus_store[span.source_id]
    actual_src_sha = sha256_bytes(raw)
    if actual_src_sha != span.source_sha256:
        return CitationVerdict(False, "REJECT", "source_sha256_mismatch", span.source_id, "")
    if span.byte_start < 0 or span.byte_end <= span.byte_start or span.byte_end > len(raw):
        return CitationVerdict(False, "REJECT", "byte_offset_out_of_bounds", span.source_id, "")
    raw_slice = raw[span.byte_start : span.byte_end]
    computed_span_sha = sha256_bytes(raw_slice)
    if computed_span_sha != span.span_sha256:
        return CitationVerdict(False, "REJECT", "span_sha256_mismatch", span.source_id, computed_span_sha)
    try:
        decoded = raw_slice.decode("utf-8")
    except UnicodeDecodeError:
        return CitationVerdict(False, "REJECT", "invalid_utf8_slice", span.source_id, computed_span_sha)
    if decoded != span.quoted_text:
        return CitationVerdict(False, "REJECT", "quoted_text_hallucination", span.source_id, computed_span_sha)
    return CitationVerdict(True, "PASS", "verified_byte_exact", span.source_id, computed_span_sha)


def verify_citation_bundle(
    spans: list[CitationSpan] | tuple[CitationSpan, ...],
    corpus_store: dict[str, bytes],
) -> dict[str, Any]:
    """Verify a bundle of citations fail-closed; empty bundles are rejected."""
    if not spans:
        return {
            "schema": "n43-citation-bundle/1",
            "ok": False,
            "verdict": "REJECT",
            "verified": 0,
            "total": 0,
            "failures": ["empty_citation_bundle"],
        }
    failures: list[str] = []
    verified = 0
    for idx, span in enumerate(spans):
        v = verify_citation_span(span, corpus_store)
        if v.ok:
            verified += 1
        else:
            failures.append(f"[{idx}:{span.source_id}] {v.reason}")
    ok = len(failures) == 0
    return {
        "schema": "n43-citation-bundle/1",
        "ok": ok,
        "verdict": "PASS" if ok else "REJECT",
        "verified": verified,
        "total": len(spans),
        "failures": failures,
    }
