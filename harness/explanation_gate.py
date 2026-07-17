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
                # keep the repo-relative path (strip only the a/ b/ diff
                # prefix): basenames collapse same-named files and split
                # the ledger's cross-kind merge against attestation paths
                if name.startswith(("a/", "b/")):
                    name = name[2:]
                name = name.replace("\\", "/")
                if name and name not in files:
                    files.append(name)
            continue
        if line[:1] in ("+", "-"):
            for ident in _IDENT.findall(line[1:]):
                if ident not in _NOISE:
                    counts[ident] = counts.get(ident, 0) + 1
    terms = [t for t, _ in sorted(counts.items(),
                                  key=lambda kv: (-kv[1], kv[0]))[:top_n]]
    return files, terms


def _own_words_ratio(diff: str, explanation: str) -> float:
    """Share of explanation word-tokens that do NOT appear in the diff's
    changed lines. Teach-back is in the reviewer's OWN words; pasting the
    diff back scores ~0 here and must not pass."""
    diff_words = set()
    for line in (diff or "").splitlines():
        if line[:1] in ("+", "-"):
            diff_words.update(w.lower() for w in _IDENT.findall(line[1:]))
    expl_words = [w.lower() for w in _IDENT.findall(explanation or "")]
    if not expl_words:
        return 0.0
    fresh = sum(1 for w in expl_words if w not in diff_words)
    return round(fresh / len(expl_words), 4)


def explanation_receipt(diff: str, explanation: str, *,
                        threshold: float = 0.6, reviewer: str = "",
                        own_words_floor: float = 0.3) -> dict:
    """Grade `explanation` against `diff` mechanically. Passing means the
    explanation names the changed files, covers at least `threshold` of the
    key changed identifiers, AND carries at least `own_words_floor` share of
    words the diff does not (so pasting the diff back cannot pass)."""
    files, terms = _key_terms(diff)
    text = (explanation or "").lower()
    mentioned = [t for t in terms if t.lower() in text]
    missed = [t for t in terms if t.lower() not in text]
    mentioned_files = [f for f in files
                       if f.lower() in text
                       or f.rsplit("/", 1)[-1].lower() in text]
    coverage = round(len(mentioned) / len(terms), 4) if terms else 0.0
    own_words_ratio = _own_words_ratio(diff, explanation)
    passed = bool(terms) and coverage >= threshold and (
        not files or bool(mentioned_files)) and (
        own_words_ratio >= own_words_floor)
    doc = {
        "schema": SCHEMA,
        "reviewer": reviewer,
        "passed": passed,
        "coverage": coverage,
        "threshold": threshold,
        "own_words_ratio": own_words_ratio,
        "own_words_floor": own_words_floor,
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
                "actual change in the reviewer's own words (a verbatim "
                "diff paste is refused), not understanding; no learned "
                "model decides",
    }
    doc["sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()
    return doc
