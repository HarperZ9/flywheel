#!/usr/bin/env python3
"""check_writing.py -- score prose against a register profile.

A sibling of check_claim_language.py. It reads a profile from writing_profiles,
counts violations per 100 words, and reports the delta between two drafts, since
the delta is the signal. It scores the FORM of prose only. A low score is not a
true document and is not proof of anything, and this tool never tries to defeat
AI detection.

Standard library only.
"""
from __future__ import annotations

import re

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE = re.compile(r"`[^`]*`")
_MATHBLOCK = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH = re.compile(r"\$[^$\n]*\$")
_SENT = re.compile(r"(?<=[.!?])(?=\s|$)")


def strip_code(text: str) -> str:
    text = _FENCE.sub(" ", text)
    text = _MATHBLOCK.sub(" ", text)
    text = _INLINE.sub(" ", text)
    text = _MATH.sub(" ", text)
    return text


def sentences(text: str) -> list[str]:
    out = []
    for chunk in _SENT.split(text):
        collapsed = " ".join(chunk.split())
        if collapsed:
            out.append(collapsed)
    return out


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


MARKETING = (
    "seamless", "seamlessly", "robust", "powerful", "cutting-edge", "effortless",
    "effortlessly", "world-class", "next-generation", "revolutionary", "blazing",
    "lightning-fast", "elegant", "delightful", "turnkey", "best-in-class",
    "state-of-the-art", "game-changing", "first-class", "battle-tested",
    "enterprise-grade", "supercharge", "unlock", "unleash", "empower", "empowers",
)
BANNED = (
    "commence", "commences", "initiate", "initiates", "utilize", "utilizes",
    "utilizing", "leverage", "leverages", "leveraging", "facilitate",
    "facilitates", "prior to", "subsequent to", "obtain", "obtains", "acquire",
    "acquires", "additionally", "furthermore", "moreover", "comprehensive",
    "aforementioned", "henceforth", "therein", "whilst", "amongst", "numerous",
    "myriad", "plethora", "in order to", "a variety of", "in the event that",
    "due to the fact that",
)
PHRASAL = (
    "spin up", "spin down", "reach out", "dive into", "dives into", "diving into",
    "kick off", "kicks off", "roll out", "rolls out", "circle back", "drill down",
)
MODAL_HEDGE = (
    "it is important to note", "it should be noted", "it is worth noting",
    "please note that", "as mentioned", "as noted above",
)
_CONTRACTION = re.compile(r"\b\w+['’](?:t|re|ve|ll|d|s|m)\b", re.IGNORECASE)
_EM_DASH = "\u2014"

# Which categories fail --gate, by slop level. Everything else is report-only,
# because passive/gerund/paragraph heuristics are noisy and would make a gate
# somebody switches off.
HARD_BY_SLOP = {
    "strict": {"em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
               "contraction", "semicolon", "long_sentence", "modal_hedge"},
    "flavored": {"em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
                 "modal_hedge"},
    "off": set(),
}

DOES_NOT_PROVE = (
    "This scores FORM, not substance. A low score is not a true or authentic "
    "document, and this tool never tries to defeat AI detection.")


def _count_phrases(low: str, phrases, keep) -> tuple[int, list]:
    total, hits = 0, []
    for phrase in phrases:
        if phrase in keep:
            continue
        for _ in re.finditer(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", low):
            total += 1
            hits.append(phrase)
    return total, hits


def check_text(text: str, profile: dict) -> dict:
    slop = profile.get("slop", "flavored")
    keep = {k.lower() for k in profile.get("keep", ())}
    prose = strip_code(text)
    low = prose.lower()
    words = count_words(prose)
    sents = sentences(prose)

    v: dict[str, int] = {}
    mk, _ = _count_phrases(low, MARKETING, keep)
    bn, _ = _count_phrases(low, BANNED, keep)
    ph, _ = _count_phrases(low, PHRASAL, keep)
    mh, _ = _count_phrases(low, MODAL_HEDGE, keep)
    if mk:
        v["marketing_adjective"] = mk
    if bn:
        v["banned_word"] = bn
    if ph:
        v["phrasal_verb"] = ph
    if mh:
        v["modal_hedge"] = mh

    em = prose.count(_EM_DASH)
    if em and profile.get("no_em_dash", True):
        v["em_dash"] = em

    semis = prose.count(";")
    if semis:
        v["semicolon"] = semis
    contr = len(_CONTRACTION.findall(prose))
    if contr:
        v["contraction"] = contr

    max_words = profile.get("max_sentence_words")
    if max_words:
        long_n = sum(1 for s in sents if count_words(s) > max_words)
        if long_n:
            v["long_sentence"] = long_n

    total = sum(v.values())
    per100w = round(total * 100.0 / words, 2) if words else 0.0
    hard_cats = HARD_BY_SLOP.get(slop, set())
    hard = sorted(c for c in v if c in hard_cats)
    return {
        "words": words, "sentences": len(sents), "violations": v,
        "total": total, "per100w": per100w, "em_dash": em, "hard": hard,
    }
