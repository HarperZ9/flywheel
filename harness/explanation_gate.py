"""explanation_gate.py -- the teach-back as a receipt.

The strongest learning result in the dossier: novices whose AI-generated
code was gated behind their own checked explanation failed a later unaided
task at 39% instead of 77% (arXiv 2602.20206). This is that gate, built to
the platform's invariant: NO learned model decides acceptance. The check is
mechanical -- the explanation must name the files that changed and a
threshold share of the identifiers the diff actually touched.

Honesty boundary, stated on every receipt: this verifies ENGAGEMENT
SPECIFICITY (the reviewer demonstrably read what changed), not deep
understanding. A model-generated probe can ride alongside as labeled prose;
it never decides. The receipt is content-addressed and store-ready, so a
commit can carry the comprehension evidence behind its acceptance.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = "flywheel.comprehension-receipt/v1"

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_NOISE = {
    "def", "return", "import", "from", "class", "self", "None", "True",
    "False", "for", "while", "else", "elif", "try", "except", "with",
    "lambda", "pass", "raise", "not", "and", "the", "int", "str", "float",
    "list", "dict", "set", "print", "len", "sum", "range",
}


def _key_terms(diff: str, top_n: int = 8) -> tuple:
    """Files and the most-touched identifiers from changed lines only."""
    files, counts = [], {}
    for line in (diff or "").splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            name = line[4:].strip()
            if name not in ("/dev/null",):
                base = name.split("/")[-1]
                if base and base not in files:
                    files.append(base)
            continue
        if line[:1] in ("+", "-"):
            for ident in _IDENT.findall(line[1:]):
                if ident not in _NOISE:
                    counts[ident] = counts.get(ident, 0) + 1
    terms = [t for t, _ in sorted(counts.items(),
                                  key=lambda kv: (-kv[1], kv[0]))[:top_n]]
    return files, terms


def explanation_receipt(diff: str, explanation: str, *,
                        threshold: float = 0.6, reviewer: str = "") -> dict:
    """Grade `explanation` against `diff` mechanically. Passing means the
    explanation names the changed files and at least `threshold` of the
    key changed identifiers."""
    files, terms = _key_terms(diff)
    text = (explanation or "").lower()
    mentioned = [t for t in terms if t.lower() in text]
    missed = [t for t in terms if t.lower() not in text]
    mentioned_files = [f for f in files if f.lower() in text]
    coverage = round(len(mentioned) / len(terms), 4) if terms else 0.0
    passed = bool(terms) and coverage >= threshold and (
        not files or bool(mentioned_files))
    doc = {
        "schema": SCHEMA,
        "reviewer": reviewer,
        "passed": passed,
        "coverage": coverage,
        "threshold": threshold,
        "key_terms": terms,
        "mentioned": mentioned,
        "missed": missed,
        "files": files,
        "mentioned_files": mentioned_files,
        "explanation_sha256": hashlib.sha256(
            (explanation or "").encode("utf-8")).hexdigest(),
        "diff_sha256": hashlib.sha256(
            (diff or "").encode("utf-8")).hexdigest(),
        "note": "mechanical gate: verifies engagement specificity with the "
                "actual change, not understanding; no learned model decides",
    }
    doc["sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()
    return doc
