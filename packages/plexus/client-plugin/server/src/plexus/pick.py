"""pick.py: choose a tool for a plain-language request, or abstain.

Each tool in the mesh becomes a short document built from its manifest: its
name, the title and summary of every capability it emits or consumes, and the
words of each capability id. A request is scored against every tool with
BM25, scores become probabilities with a softmax, and the top tool is picked
only when its probability reaches ``threshold``. Otherwise the result is
ABSTAIN: ``picked`` is None and ``abstained`` is True, so a person or a larger
model decides. Deterministic: ties break by tool name.
"""
from __future__ import annotations

import math
import re

from .mesh import Mesh

SCHEMA = "plexus.pick/1"
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by can do for from how i in into is it its me my of on "
    "or our please so that the this to up us we what when which why will with you "
    "your v1 v2 1 2".split()
)


def _stem(word: str) -> str:
    for suffix in ("ing", "ies", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def terms(text: str) -> list[str]:
    """Lowercase word tokens, stop words dropped, light suffix stemming."""
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def tool_document(manifest) -> list[str]:
    parts = [manifest.organ.replace("-", " ")]
    for port in list(manifest.emits) + list(manifest.consumes):
        parts.extend([port.title, port.summary, port.capability])
    return terms(" ".join(parts))


def _bm25(docs: list[list[str]], query: list[str], k1: float = 1.2,
          b: float = 0.75) -> list[float]:
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n if n else 0.0
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    out = []
    for doc in docs:
        total = 0.0
        for t in set(query):
            f = doc.count(t)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                total += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(doc) / (avgdl or 1)))
        out.append(total)
    return out


def _softmax(scores: list[float], temperature: float) -> list[float]:
    if not scores:
        return []
    top = max(scores)
    exps = [math.exp((s - top) / temperature) for s in scores]
    z = sum(exps)
    return [e / z for e in exps]


def rank_tools(mesh: Mesh, request: str, temperature: float = 1.0) -> list[dict]:
    """Every tool with its raw score and probability, best first."""
    organs = sorted(mesh.manifests)
    raw = _bm25([tool_document(mesh.manifests[o]) for o in organs], terms(request))
    probs = _softmax(raw, temperature)
    rows = [{"tool": o, "score": round(r, 6), "probability": round(p, 6)}
            for o, r, p in zip(organs, raw, probs)]
    rows.sort(key=lambda row: (-row["probability"], row["tool"]))
    return rows


DEFAULT_THRESHOLD = 0.23   # the dev-half calibration on the labelled set, docs/PICK.md


def pick(mesh: Mesh, request: str, *, threshold: float = DEFAULT_THRESHOLD,
         temperature: float = 1.0) -> dict:
    """Pick a tool for ``request`` or abstain. Returns a JSON-ready dict.

    The default threshold is the value the dev-half calibration chose. A
    threshold of 0.0 abstains only when no tool shares a word with the request.
    """
    if not 0.0 <= threshold <= 1.0 or temperature <= 0:
        raise ValueError("threshold must be in [0, 1] and temperature > 0")
    rows = rank_tools(mesh, request, temperature)
    top = rows[0] if rows else None
    abstained = top is None or top["score"] <= 0 or top["probability"] < threshold
    return {"schema": SCHEMA, "request": request, "threshold": threshold,
            "picked": None if abstained else top["tool"], "abstained": abstained,
            "confidence": top["probability"] if top else 0.0, "candidates": rows}
