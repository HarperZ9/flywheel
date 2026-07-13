"""memory_api.py -- the durable memory surface over the fold index.

One content-addressed store per run root (<run_root>/fold_index.json): the
same index the compaction loop folds spans into, opened here for stats,
recall, and durable notes. Recall is verbatim spans with provenance (the
span hash IS the content address), never a paraphrase. An empty store
reports itself empty."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .fold_index import FoldIndex


def _store(run_root: "Path | str") -> FoldIndex:
    return FoldIndex(Path(run_root) / "fold_index.json")


def memory_stats(run_root: "Path | str") -> dict:
    idx = _store(run_root)
    return {"schema": "flywheel.memory/v1",
            "spans": len(idx.spans),
            "terms": len(idx.postings),
            "persisted": bool(idx.path and idx.path.exists())}


def memory_recall(run_root: "Path | str", query: str, top_k: int = 5) -> dict:
    idx = _store(run_root)
    results = idx.recall(query, top_k=max(1, min(int(top_k or 5), 20)))
    return {"schema": "flywheel.memory-recall/v1", "query": query,
            "results": results, "n": len(results)}


def memory_note(run_root: "Path | str", content: str, role: str = "note") -> dict:
    """Store a durable note. Content-addressed: the same content is never
    stored twice, and the returned span hash re-derives from the content."""
    text = (content or "").strip()
    if not text:
        return {"error": "empty note"}
    span_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    idx = _store(run_root)
    existed = span_hash in idx.spans
    idx.add(span_hash, [{"role": role, "content": text}])
    return {"schema": "flywheel.memory-note/v1", "span_hash": span_hash,
            "existed": existed, "spans": len(idx.spans)}
