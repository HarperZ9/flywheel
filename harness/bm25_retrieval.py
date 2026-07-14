"""bm25_retrieval.py -- retrieval that cites its evidence. Zero-dep.

Semble (new-entrant sweep) showed CPU-only hybrid retrieval beating
grep-and-read on token cost; its README numbers stay in its README. This
is the honest local core: BM25 over line-window chunks of a repo, each
hit carrying file, starting line, and the chunk's content hash -- so a
snippet the model cites is re-checkable against the exact text retrieved,
and a stale index is detectable by hash. Embedding fusion can join later;
a ranking that cannot cite its evidence does not ship at all.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

SCHEMA = "flywheel.retrieval-hit/v1"
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
_WINDOW = 40          # lines per chunk
_K1, _B = 1.5, 0.75
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".dart_tool", "build",
              "artifacts", ".pytest_cache", ".ruff_cache"}
_EXTS = {".py", ".dart", ".js", ".ts", ".mjs", ".md", ".rs", ".go", ".java",
         ".c", ".h", ".cpp", ".rb", ".lean", ".toml", ".yaml", ".yml"}


def _tokens(text: str) -> list:
    return [t.lower() for t in _TOKEN.findall(text)]


def build_index(root, *, max_files: int = 3000,
                max_bytes: int = 1_000_000) -> dict:
    """Chunk the repo into line windows and build BM25 statistics. Caps
    are part of the result: skipped files are counted, never silent."""
    root = Path(root)
    chunks: list = []
    skipped = 0
    counted = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in _EXTS:
            continue
        rel = p.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if counted >= max_files or p.stat().st_size > max_bytes:
            skipped += 1
            continue
        try:
            lines = p.read_text(encoding="utf-8",
                                errors="ignore").splitlines()
        except OSError:
            skipped += 1
            continue
        counted += 1
        for start in range(0, max(len(lines), 1), _WINDOW):
            text = "\n".join(lines[start:start + _WINDOW])
            if text.strip():
                chunks.append({"path": rel.as_posix(), "line": start + 1,
                               "text": text, "tokens": _tokens(text)})
    df: dict = {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1
    avg_len = (sum(len(c["tokens"]) for c in chunks) / len(chunks)
               if chunks else 0.0)
    return {"chunks": chunks, "df": df, "n": len(chunks),
            "avg_len": avg_len, "files": counted, "skipped": skipped}


def search(index: dict, query: str, k: int = 8) -> list:
    """BM25 top-k, ties broken by path+line so ranking is deterministic.
    A hit is a receipt: path, line, excerpt, and the chunk's hash."""
    q = _tokens(query)
    n = index["n"]
    if not q or not n:
        return []
    scored: list = []
    for c in index["chunks"]:
        length = len(c["tokens"]) or 1
        score = 0.0
        for t in q:
            tf = c["tokens"].count(t)
            if not tf:
                continue
            idf = math.log(1 + (n - index["df"].get(t, 0) + 0.5)
                           / (index["df"].get(t, 0) + 0.5))
            score += idf * (tf * (_K1 + 1)) / (
                tf + _K1 * (1 - _B + _B * length / (index["avg_len"] or 1)))
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda sc: (-sc[0], sc[1]["path"], sc[1]["line"]))
    return [{"schema": SCHEMA, "path": c["path"], "line": c["line"],
             "score": round(s, 4),
             "excerpt": c["text"][:400],
             "sha256": hashlib.sha256(c["text"].encode("utf-8")).hexdigest()}
            for s, c in scored[:k]]
