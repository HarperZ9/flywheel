"""fold_index.py — recall exact facts from compacted context, no embeddings.

Compaction folds old turns into a summary and keeps only their hash. This stores
the folded ORIGINAL messages content-addressed by their span hash, plus a stdlib
inverted index, so a specific fact from earlier in a long session can be recalled
VERBATIM even after it was folded. A Mem0 / HippoRAG-class capability without a
vector database, without embeddings, and without any learned model on any path.
Persisted as one JSON file so it survives restarts. Zero-dep.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> list:
    return _WORD.findall((text or "").lower())


def _content_hash(messages: list) -> str:
    """A content hash DERIVED from the stored span, so recall binds to what
    is actually held rather than to a hash the caller merely asserted."""
    return hashlib.sha256(
        json.dumps(messages, sort_keys=True, default=str).encode()).hexdigest()


class FoldIndex:
    """Content-addressed store of folded message spans + an inverted term index."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.spans: dict = {}                       # span_hash -> [ {role, content}, ... ]
        self.postings: dict = defaultdict(set)      # term -> {span_hash}
        self._content: dict = {}                    # span_hash -> derived content hash (banked at add)
        if self.path and self.path.exists():
            self._load()

    def add(self, span_hash: str, messages: list) -> None:
        if not span_hash or span_hash in self.spans:
            return                                  # content-addressed: never index the same span twice
        self.spans[span_hash] = messages
        self._content[span_hash] = _content_hash(messages)
        text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
        for t in set(_terms(text)):
            self.postings[t].add(span_hash)
        self._save()

    def recall(self, query: str, *, top_k: int = 3) -> list:
        """Return the top-k folded spans matching the query, ranked by a stdlib
        idf-weighted term overlap (rarer terms count for more). Verbatim messages."""
        q_terms = set(_terms(query))
        if not q_terms or not self.spans:
            return []
        n = len(self.spans)
        scores: "Counter" = Counter()
        for t in q_terms:
            hits = self.postings.get(t)
            if not hits:
                continue
            idf = math.log((n + 1) / (len(hits) + 1)) + 1.0
            for sh in hits:
                scores[sh] += idf
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        return [{"span_hash": sh, "score": round(s, 4),
                 "messages": self.spans[sh],
                 "content_sha256": _content_hash(self.spans[sh])}
                for sh, s in ranked]

    def verify(self) -> dict:
        """Re-derive each span's content hash and report any whose stored
        content no longer matches what was banked. Catches a tampered
        fold_index.json that verify would otherwise trust."""
        tampered = [sh for sh, msgs in self.spans.items()
                    if _content_hash(msgs) != self._content.get(sh)]
        return {"schema": "flywheel.fold-index-verify/v1",
                "ok": not tampered, "checked": len(self.spans),
                "tampered": tampered}

    def _snapshot(self) -> dict:
        return {"schema": "flywheel.fold-index/v1", "spans": self.spans,
                "content": self._content,
                "postings": {t: sorted(v) for t, v in self.postings.items()}}

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._snapshot(), sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        d = json.loads(self.path.read_text(encoding="utf-8"))
        self.spans = d.get("spans", {})
        # banked content hashes; for a pre-content index, derive on load so
        # verify has a baseline (a persisted index tampered before this
        # upgrade still gets a fresh baseline, which is the honest floor)
        self._content = d.get("content") or {
            sh: _content_hash(m) for sh, m in self.spans.items()}
        self.postings = defaultdict(set, {t: set(v) for t, v in d.get("postings", {}).items()})


def index_compaction(fold_index: FoldIndex, original_messages: list, result) -> "str | None":
    """Extract the span a compaction folded away and index it for later recall.
    Uses the receipt's kept_head/kept_recent/pin_roles to reconstruct exactly what
    was folded (pinned messages were kept, so they are not re-indexed here)."""
    r = result.receipt
    if not result.compacted or r.get("method") == "noop":
        return None
    from .compaction import _is_pinned
    orig = list(original_messages)
    kh, kr = r["kept_head"], r["kept_recent"]
    pins = r.get("pin_roles", [])
    middle = orig[kh: len(orig) - kr] if kr else orig[kh:]
    foldable = [m for m in middle if not _is_pinned(m, pins)]
    span_hash = r.get("summarized_span_sha256")
    if span_hash:
        fold_index.add(span_hash, foldable)
    return span_hash
