"""daemon.py -- the watchlist poller: re-synthesize discourse when a corpus grows.

A watchlist names gathered corpora to keep an eye on. Each tick, for each watched
corpus, the daemon computes the corpus's input signature (the same content hash the
receipt binds); if it is unchanged since the last synthesis, the tick is a no-op,
so nothing re-runs until there is genuinely new discourse. When a corpus has grown
or changed, the daemon runs the lens and stores a receipted digest, then advances
the cursor -- in that order, so a crash between the two re-synthesizes rather than
skips (no receipt, no accept, applies to the store too).

The tick is deterministic given the same corpora (the clock is injected and only
stamps store metadata, never the digest). The interval loop that calls it on a
schedule is a thin wrapper in the CLI.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from chorus.item import normalize
from chorus.receipt import input_digest
from chorus.sentiment import score
from chorus.synthesize import synthesize


class Watchlist:
    """The set of corpora to watch, order-preserving and de-duplicated."""

    def __init__(self, sources: list[str] | None = None) -> None:
        self.sources: list[str] = []
        for s in sources or []:
            self.add(s)

    def add(self, source: str) -> None:
        if source and source not in self.sources:
            self.sources.append(source)

    def remove(self, source: str) -> None:
        self.sources = [s for s in self.sources if s != source]

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"sources": self.sources}, f, indent=1)

    @classmethod
    def load(cls, path: str) -> "Watchlist":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        src = data.get("sources") if isinstance(data, dict) else data
        return cls(src if isinstance(src, list) else [])


class DigestStore:
    """A directory of stored digests: one JSON file per digest (by its own hash),
    an append-only index, and a per-corpus cursor of the last-synthesized signature.
    """

    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(os.path.join(root, "digests"), exist_ok=True)

    @property
    def _index(self) -> str:
        return os.path.join(self.root, "index.jsonl")

    @property
    def _cursors(self) -> str:
        return os.path.join(self.root, "cursors.json")

    def cursor(self, corpus: str) -> "str | None":
        try:
            with open(self._cursors, encoding="utf-8") as f:
                return json.load(f).get(corpus)
        except (OSError, ValueError):
            return None

    def set_cursor(self, corpus: str, signature: str) -> None:
        cur = {}
        try:
            with open(self._cursors, encoding="utf-8") as f:
                cur = json.load(f)
        except (OSError, ValueError):
            cur = {}
        cur[corpus] = signature
        with open(self._cursors, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=1)

    def store(self, corpus: str, digest, *, at: float) -> dict:
        """Write the full digest by its own hash, then append an index row. The
        digest file lands before the index row, so a partial store leaves an
        orphan digest (harmless) rather than an index row pointing at nothing."""
        sha = digest.receipt.digest_sha256
        path = os.path.join(self.root, "digests", f"{sha}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_digest_to_dict(digest), f, ensure_ascii=False)
        row = {"at": at, "corpus": corpus, "responds_to": digest.responds_to,
               "n_items": digest.n_items, "themes": len(digest.themes),
               "verified": True, "digest_sha256": sha}
        with open(self._index, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def recent(self, limit: int = 20) -> list[dict]:
        try:
            with open(self._index, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return []
        return list(reversed(rows))[:limit]


def _digest_to_dict(digest) -> dict:
    d = asdict(digest)
    return d


def _load_rows(corpus: str) -> list[dict]:
    from chorus.cli import _load_rows as load
    return load(corpus)


def tick(watchlist: Watchlist, store: DigestStore, *,
         clock=time.time, verify: bool = True) -> dict:
    """One poll over the watchlist. Synthesizes any corpus whose content changed
    since its stored cursor; a bad corpus is named and skipped without advancing.
    Returns a per-corpus summary."""
    results = []
    for corpus in watchlist.sources:
        try:
            rows = _load_rows(corpus)
            scored = score(normalize(rows))
        except (OSError, ValueError) as e:
            results.append({"corpus": corpus, "status": "error", "detail": str(e)})
            continue
        signature = input_digest(scored)
        if store.cursor(corpus) == signature:
            results.append({"corpus": corpus, "status": "unchanged"})
            continue
        digest = synthesize(scored)
        store.store(corpus, digest, at=float(clock()))   # digest first,
        store.set_cursor(corpus, signature)              # then advance the cursor
        results.append({"corpus": corpus, "status": "synthesized",
                        "n_items": digest.n_items, "themes": len(digest.themes)})
    return {"ticked": len(watchlist.sources), "results": results}
