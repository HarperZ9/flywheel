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

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing_profiles as _wp  # noqa: E402

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
# Possessive 's is not a contraction. The 's form is a contraction only after a
# closed set of pronouns; the other suffixes stay general.
_CONTRACTION = re.compile(
    r"\b\w+['\u2019](?:t|re|ve|ll|d|m)\b"
    r"|\b(?:it|that|there|here|he|she|what|who|let)['\u2019]s\b",
    re.IGNORECASE)
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


def _count_phrases(low: str, phrases, keep) -> int:
    total = 0
    for phrase in phrases:
        if phrase in keep:
            continue
        total += len(re.findall(
            r"(?<![a-z0-9_])" + re.escape(phrase) + r"(?![a-z0-9_])", low))
    return total


def check_text(text: str, profile: dict) -> dict:
    slop = profile.get("slop", "flavored")
    keep = {k.lower() for k in profile.get("keep", ())}
    prose = strip_code(text)
    low = re.sub(r"\s+", " ", prose.lower())
    words = count_words(prose)
    sents = sentences(prose)

    v: dict[str, int] = {}
    mk = _count_phrases(low, MARKETING, keep)
    bn = _count_phrases(low, BANNED, keep)
    ph = _count_phrases(low, PHRASAL, keep)
    mh = _count_phrases(low, MODAL_HEDGE, keep)
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


def score_file(path: str, profile: dict) -> dict:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    rec = check_text(text, profile)
    rec["path"] = str(path)
    return rec


def delta(old_text: str, new_text: str, profile: dict) -> dict:
    old = check_text(old_text, profile)["per100w"]
    new = check_text(new_text, profile)["per100w"]
    return {"old": old, "new": new, "delta": round(new - old, 2)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--delta", nargs=2, metavar=("OLD", "NEW"))
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on any hard violation; otherwise report only")
    args = ap.parse_args(argv)

    def resolve(path: str) -> dict:
        name = args.profile or _wp.profile_for(path)
        return _wp.load(name)

    if args.delta:
        old_p, new_p = args.delta
        prof = _wp.load(args.profile or _wp.profile_for(new_p))
        d = delta(Path(old_p).read_text(encoding="utf-8", errors="replace"),
                  Path(new_p).read_text(encoding="utf-8", errors="replace"), prof)
        print(json.dumps(d) if args.as_json
              else f"delta per100w: {d['old']} -> {d['new']} ({d['delta']:+})")
        if args.gate and check_text(
                Path(new_p).read_text(encoding="utf-8", errors="replace"),
                prof)["hard"]:
            return 1
        return 0

    records = [score_file(f, resolve(f)) for f in args.files]
    any_hard = any(r["hard"] for r in records)
    if args.as_json:
        print(json.dumps({"files": records, "does_not_prove": DOES_NOT_PROVE},
                         indent=1))
    else:
        for r in records:
            prof_name = args.profile or _wp.profile_for(r["path"])
            print(f"{r['path']}  profile={prof_name} words={r['words']} "
                  f"total={r['total']} per100w={r['per100w']} "
                  f"em_dash={r['em_dash']} hard={','.join(r['hard']) or '-'}")
        print(DOES_NOT_PROVE)
    return 1 if (args.gate and any_hard) else 0


if __name__ == "__main__":
    sys.exit(main())
