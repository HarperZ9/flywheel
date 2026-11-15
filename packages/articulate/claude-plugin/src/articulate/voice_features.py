"""Measures of one text for the author-voice profile.

Every value is an aggregate: a rate per 1,000 words, a share of sentences, a
quantile of lengths. No sentence, phrase or name leaves this module.
"""
import re
from collections import Counter

from . import corpus_features as cf
from . import detector
from .wordlists import FUNCTION_WORDS

CONCESSION = re.compile(r"(?i)\b(?:but|though|although|yet)\b")
CAUSAL = re.compile(r"(?i)\b(?:because|so|since)\b")
CONDITIONAL = re.compile(r"(?i)\b(?:if|unless)\b")
CONTRACTION = re.compile(r"(?i)\b\w+(?:n't|'re|'ve|'ll|'m|'d)\b"
                         r"|\b(?:it|that|there|here|what|who|he|she|let)'s\b")
_WH = frozenset({"who", "what", "why", "how", "where", "when", "which"})
_CONJ = frozenset({"and", "but", "or", "so", "yet", "because", "though", "although", "if",
                   "when", "while", "since", "unless", "nor"})
_PRON = frozenset({"you", "he", "she", "it", "they", "this", "that", "these", "those",
                   "there", "here", "one", "someone", "everyone", "nobody", "it's"})
_ADV = frozenset({"then", "now", "still", "also", "just", "even", "only", "perhaps", "maybe",
                  "once", "today", "yesterday", "sometimes", "often", "again", "later"})
OPENING_CLASSES = ("i", "we", "pronoun", "conjunction", "adverb", "article", "question_word",
                   "number", "other")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9']*")


def _normalize(text):
    return text.replace("’", "'").replace("‘", "'")


def opening_class(sentence):
    tokens = _TOKEN.findall(detector.strip_markup(_normalize(sentence)))
    if not tokens:
        return "other"
    first = tokens[0]
    low = first.lower()
    if first[0].isdigit():
        return "number"
    if first in ("I", "I'm", "I've", "I'd", "I'll") or low in ("my", "me"):
        return "i"
    if low in ("we", "our", "us", "we're", "we've", "we'd", "we'll"):
        return "we"
    if low in _WH and sentence.rstrip().endswith("?"):
        return "question_word"
    for name, words in (("conjunction", _CONJ), ("pronoun", _PRON), ("adverb", _ADV)):
        if low in words:
            return name
    if low.endswith("ly") and len(low) > 4:
        return "adverb"
    if low in ("a", "an", "the"):
        return "article"
    return "other"


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round(p / 100 * (len(ordered) - 1))]


def quantiles(values):
    return {str(p): percentile(values, p) for p in (10, 25, 50, 75, 90)}


def _per_1k(count, total):
    return round(count * 1000 / total, 2) if total else 0.0


def sentences_of(text):
    return [s for b in cf.prose_blocks(_normalize(text)) for s in cf.sentences(b["text"])
            if cf.words(s)]


def measure(text):
    """All per-text measures, as plain numbers and counters."""
    text = _normalize(text)
    sents = sentences_of(text)
    paras = [len(cf.words(b["text"])) for b in cf.prose_blocks(text)]
    tokens = [w.lower() for s in sents for w in cf.words(s)]
    total = len(tokens)
    prose = "\n".join(sents)
    singular, plural = cf.first_person(prose)
    openings = Counter(opening_class(s) for s in sents)
    firsts = Counter(t[0].lower() for s in sents for t in [cf.words(s)] if t and t[0].lower() in FUNCTION_WORDS)
    moves = Counter(cf.label(s) for s in sents)
    return {"words": total, "sentence_lengths": [len(cf.words(s)) for s in sents],
            "paragraph_lengths": paras, "sentences": len(sents),
            "openings": openings, "opening_words": firsts, "moves": moves,
            "function_words": Counter(t for t in tokens if t in FUNCTION_WORDS),
            "rates": {"first_person_per_1k": _per_1k(singular, total),
                      "author_we_per_1k": _per_1k(plural, total),
                      "questions_per_1k": _per_1k(sum(s.rstrip().endswith("?") for s in sents), total),
                      "contractions_per_1k": _per_1k(len(CONTRACTION.findall(prose)), total),
                      "concession_per_1k": _per_1k(len(CONCESSION.findall(prose)), total),
                      "causal_per_1k": _per_1k(len(CAUSAL.findall(prose)), total),
                      "conditional_per_1k": _per_1k(len(CONDITIONAL.findall(prose)), total),
                      "hedges_per_1k": _per_1k(len(detector.HEDGE_WORDS.findall(prose)), total)}}


def scalars(m):
    """The scalar features compare uses, from one measure() result."""
    n = m["sentences"] or 1
    out = {"sentence_len_median": percentile(m["sentence_lengths"], 50) or 0,
           "sentence_len_cv": cf.cv(m["sentence_lengths"]) or 0.0,
           "paragraph_len_median": percentile(m["paragraph_lengths"], 50) or 0,
           "paragraph_len_cv": cf.cv(m["paragraph_lengths"]) or 0.0}
    out.update(m["rates"])
    out["opens_with_i_share"] = round(m["openings"].get("i", 0) / n, 3)
    out["opens_with_conjunction_share"] = round(m["openings"].get("conjunction", 0) / n, 3)
    return out


SCALAR_NAMES = tuple(scalars(measure("One two three four. Five six seven eight.")))


def name_like(texts):
    """Lowercase forms of words that appear capitalized away from a sentence start."""
    names = set()
    for text in texts:
        for s in sentences_of(text):
            for i, w in enumerate(cf.words(s)):
                if i and w[:1].isupper() and w != "I":
                    names.add(w.lower())
    return names


def vocabulary(texts, limit=50):
    """Content words used 3 or more times across 2 or more samples, names removed."""
    names = name_like(texts)
    per_sample = [Counter(w.lower() for s in sentences_of(t) for w in cf.words(s)
                          if len(w) >= 4 and w.isalpha()) for t in texts]
    total = Counter()
    for c in per_sample:
        total.update(c)
    keep = [w for w, n in total.items() if n >= 3 and w not in FUNCTION_WORDS and w not in names
            and sum(1 for c in per_sample if c[w]) >= 2]
    return sorted(keep, key=lambda w: (-total[w], w))[:limit]
