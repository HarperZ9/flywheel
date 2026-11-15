"""Receipts for series review and voice comparison that anyone can replay.

articulate/corpus-receipt/v1 records each document's hash, the corpus
fingerprint (thresholds, move cues, title rules, word lists and the style-rule
fingerprint), the keep list and the findings. verify_corpus_receipt re-runs
the analysis on the same texts and answers Match, Drift or Unverifiable, the
same lattice as the single-document receipt. A voice comparison record replays
the same way from the draft and the stored profile.

The single-document ruleset fingerprint does not move, so every earlier
receipt still verifies.
"""
import hashlib
import json

from . import corpus, corpus_features, detector, titles, wordlists
from . import voice
from .scope import without_scope

SCHEMA = "articulate/corpus-receipt/v2"
SCHEMA_V1 = "articulate/corpus-receipt/v1"
CORPUS_RULESET_SEMVER = "0.8.0"
SCOPE = ("Re-runs the same rules on the same texts. Match means the findings are the "
         "same as in the receipt.")


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def corpus_fingerprint():
    """A short hash of every rule the series checks read."""
    material = {"semver": CORPUS_RULESET_SEMVER,
                "thresholds": corpus_features.THRESHOLDS,
                "argued": sorted(corpus_features.ARGUED_GENRES),
                "moves": corpus_features.MOVE_CUES,
                "title_rules": titles.FAMILY_RULES,
                "title_closed": sorted(wordlists.TITLE_CLOSED),
                "function_words": _sha(" ".join(sorted(wordlists.FUNCTION_WORDS))),
                "detector": detector.ruleset_fingerprint()}
    return "sha256:" + hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()[:16]


def _pkg_version():
    from . import __version__
    return __version__


def make_corpus_receipt(docs, *, keep=(), genre="essay", single=False, report=None):
    report = report or corpus.analyze_corpus(docs, keep=keep, genre=genre, single=single)
    return {"schema": SCHEMA, "articulate_version": _pkg_version(),
            "corpus_ruleset": CORPUS_RULESET_SEMVER, "corpus_fingerprint": corpus_fingerprint(),
            "documents": [{"name": d["name"], "text_sha256": _sha(d["text"])} for d in docs],
            "keep": list(report["keep"]), "keep_sha256": _sha(_canonical(list(report["keep"]))),
            "genre": genre, "single": bool(single), "findings": report["findings"],
            "ai_detector_consulted": False, "scope": SCOPE}


def _same_documents(receipt, docs):
    want = {d.get("name"): d.get("text_sha256") for d in receipt.get("documents", [])}
    have = {d["name"]: _sha(d["text"]) for d in docs}
    if set(want) != set(have):
        return "the documents named in the receipt differ from those given"
    changed = sorted(n for n in want if want[n] != have[n])
    if changed:
        return "text hash does not match for " + ", ".join(changed)
    return None


def verify_corpus_receipt(receipt, docs):
    """(verdict, detail) for a corpus receipt replayed against docs."""
    if not isinstance(receipt, dict) or receipt.get("schema") not in (SCHEMA, SCHEMA_V1):
        return "Unverifiable", "unknown or missing corpus receipt schema"
    current = corpus_fingerprint()
    if receipt.get("corpus_fingerprint") != current:
        return "Unverifiable", (f"corpus fingerprint changed ({receipt.get('corpus_fingerprint')} "
                                f"-> {current}); cannot re-derive under different rules")
    problem = _same_documents(receipt, docs)
    if problem:
        return "Unverifiable", problem
    if _sha(_canonical(receipt.get("keep", []))) != receipt.get("keep_sha256"):
        return "Unverifiable", "keep list does not match its hash"
    order = {d["name"]: i for i, d in enumerate(receipt["documents"])}
    docs = sorted(docs, key=lambda d: order[d["name"]])
    again = corpus.analyze_corpus(docs, keep=receipt["keep"], genre=receipt.get("genre", "essay"),
                                  single=receipt.get("single", False))
    have, want = again["findings"], receipt.get("findings")
    if receipt["schema"] == SCHEMA_V1:
        # A version 1 receipt names each finding's scope does_not_prove, in
        # older words, so the comparison leaves the scope fields out.
        have, want = without_scope(have), without_scope(want)
    if have != want:
        return "Drift", "re-derived findings differ from the receipt"
    return "Match", f"re-derived {len(again['findings'])} findings over {len(docs)} documents"


def verify_voice_compare(record, text, profile):
    """(verdict, detail) for a voice comparison replayed from draft and profile."""
    if not isinstance(record, dict) or record.get("schema") not in (voice.COMPARE_SCHEMA,
                                                                    voice.COMPARE_SCHEMA_V1):
        return "Unverifiable", "unknown or missing voice comparison schema"
    if record.get("draft_sha256") != voice.sha256(text):
        return "Unverifiable", "draft does not match the record's hash"
    if record.get("profile_sha256") != voice.sha256(voice.canonical(profile)):
        return "Unverifiable", "profile does not match the record's hash"
    again = voice.compare(text, profile)
    if record["schema"] == voice.COMPARE_SCHEMA_V1:
        # A version 1 record names its scope does_not_prove, in older words.
        again = without_scope(dict(again, schema=record["schema"]))
        record = without_scope(record)
    if again != record:
        return "Drift", "re-derived comparison differs from the record"
    return "Match", f"re-derived {len(record['features'])} feature verdicts"
