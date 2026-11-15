"""The author-voice profile: built from samples the author names, stored as
aggregates, described in plain words, and compared against a draft.

build_profile keeps rates, shares and quantiles, never a sentence. compare
says, feature by feature, whether a draft sits inside, above or below the
range the author's own samples span, and points at lines where an author who
writes in the first person goes a long way without it. It returns no total,
no distance and no rewritten text.

Standard library only. No network, no model, no detector service.
"""
import hashlib
import json
from collections import Counter

from . import corpus_features as cf
from . import voice_features as vf

SCHEMA = "articulate/voice-profile/v1"
COMPARE_SCHEMA = "articulate/voice-compare/v2"
COMPARE_SCHEMA_V1 = "articulate/voice-compare/v1"
INDICATIVE_WORDS = 5000
COMPARE_LIMIT = ("Places each feature of the draft against your measured range. Use it to "
                 "see where to look.")
RARE_OPENING = 0.02


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _shares(counter, total, keys=None):
    keys = keys if keys is not None else sorted(counter)
    return {k: round(counter.get(k, 0) / total, 3) if total else 0.0 for k in keys}


def _pool(measures):
    pooled = {"sentence_lengths": [], "paragraph_lengths": []}
    counters = {k: Counter() for k in ("openings", "opening_words", "moves", "function_words")}
    for m in measures:
        pooled["sentence_lengths"] += m["sentence_lengths"]
        pooled["paragraph_lengths"] += m["paragraph_lengths"]
        for k in counters:
            counters[k].update(m[k])
    return pooled, counters


def _spread(per_sample, key):
    values = [s[key] for s in per_sample]
    return {"min": min(values), "max": max(values)}


def build_profile(samples, *, vocabulary=True):
    """Profile from a list of sample texts. Raises ValueError without prose."""
    if not isinstance(samples, list) or not samples or not all(isinstance(s, str) for s in samples):
        raise ValueError("voice learn needs one or more text samples")
    measures = [vf.measure(s) for s in samples]
    words = sum(m["words"] for m in measures)
    if not words:
        raise ValueError("the samples hold no prose to measure")
    pooled, counters = _pool(measures)
    sents = sum(m["sentences"] for m in measures)
    per_sample = [vf.scalars(m) for m in measures]
    rates = {k: round(sum(m["rates"][k] * m["words"] for m in measures) / words, 2)
             for k in measures[0]["rates"]}
    top_fw = counters["function_words"].most_common(100)
    profile = {
        "schema": SCHEMA,
        "sources": {"samples": [{"sha256": sha256(s), "words": m["words"]}
                                for s, m in zip(samples, measures)],
                    "total_words": words, "indicative_only": words < INDICATIVE_WORDS,
                    "vocabulary_basis": "own-samples"},
        "rhythm": {"sentence_quantiles": vf.quantiles(pooled["sentence_lengths"]),
                   "sentence_cv": cf.cv(pooled["sentence_lengths"]),
                   "paragraph_quantiles": vf.quantiles(pooled["paragraph_lengths"]),
                   "paragraph_cv": cf.cv(pooled["paragraph_lengths"]),
                   "spread": {k: _spread(per_sample, k) for k in
                              ("sentence_len_median", "sentence_len_cv",
                               "paragraph_len_median", "paragraph_len_cv")}},
        "openings": {"classes": _shares(counters["openings"], sents, vf.OPENING_CLASSES),
                     "top_words": _shares(counters["opening_words"], sents,
                                          [w for w, _ in counters["opening_words"].most_common(15)])},
        "argument": dict(rates, move_mix=_shares(counters["moves"], sents)),
        "function_words": {w: round(n * 1000 / words, 2) for w, n in top_fw},
        "per_sample": per_sample,
    }
    if vocabulary:
        profile["vocabulary"] = {"basis": "own-samples", "words": vf.vocabulary(samples)}
    return profile


def _range(profile, key):
    values = [s[key] for s in profile["per_sample"]]
    low, high = min(values), max(values)
    margin = max(0.1 * (high - low), 0.05 * abs((low + high) / 2))
    # Every scalar is a count, length, rate or share, so the widened range stops
    # at 0, and a share stops at 1.
    ceiling = 1.0 if key.endswith("_share") else float("inf")
    return round(max(0.0, low - margin), 3), round(min(ceiling, high + margin), 3)


def _rare_openings(text, profile):
    shares = profile["openings"]["classes"]
    rare = {c for c, share in shares.items() if share < RARE_OPENING and c != "other"}
    out = []
    for b in cf.prose_blocks(vf._normalize(text)):
        found = Counter(vf.opening_class(s) for s in cf.sentences(b["text"]))
        for cls in sorted(rare):
            if found[cls] >= 3:
                out.append({"kind": "rare-opening", "line_start": b["line_start"],
                            "line_end": b["line_end"],
                            "measure": {"opening_class": cls, "count": found[cls],
                                        "your_share": shares[cls]}})
    return out


def _locations(text, profile):
    out = []
    uses_first_person = min(s["first_person_per_1k"] for s in profile["per_sample"]) >= 1.0
    if uses_first_person:
        for n, a, b in cf.author_stretches(vf._normalize(text)):
            if n > cf.THRESHOLDS["perspective_stretch"]:
                out.append({"kind": "no-first-person-stretch", "line_start": a, "line_end": b,
                            "measure": {"words": n}})
    return out + _rare_openings(text, profile)


def compare(text, profile):
    """Per-feature inside/above/below against the author's own sample range."""
    if not isinstance(text, str):
        raise ValueError("compare needs draft text")
    if not isinstance(profile, dict) or profile.get("schema") != SCHEMA:
        raise ValueError("not an articulate voice profile")
    value = vf.scalars(vf.measure(text))
    features = []
    for key in vf.SCALAR_NAMES:
        low, high = _range(profile, key)
        verdict = "below" if value[key] < low else "above" if value[key] > high else "inside"
        features.append({"feature": key, "low": low, "high": high, "value": value[key],
                         "verdict": verdict})
    return {"schema": COMPARE_SCHEMA, "draft_sha256": sha256(text),
            "profile_sha256": sha256(canonical(profile)), "features": features,
            "locations": _locations(text, profile),
            "indicative_only": profile["sources"]["indicative_only"],
            "ai_detector_consulted": False, "scope": COMPARE_LIMIT}


def describe(profile):
    """Every stored field, in plain sentences."""
    from .voice_text import describe as _describe
    return _describe(profile)
