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
import writing_pysource as _ps  # noqa: E402
from writing_lists import BANNED, MARKETING, MODAL_HEDGE, PHRASAL  # noqa: E402
from writing_readability import reading_ease, syllables  # noqa: E402  # re-exported for CW.syllables callers

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


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


# Possessive 's is not a contraction. The 's form is a contraction only after a
# closed set of pronouns; the other suffixes stay general.
_CONTRACTION = re.compile(
    r"\b\w+['\u2019](?:t|re|ve|ll|d|m)\b"
    r"|\b(?:it|that|there|here|he|she|what|who|let)['\u2019]s\b",
    re.IGNORECASE)
_EM_DASH = "\u2014"

_BE = r"(?:am|is|are|was|were|be|been|being)"
_BE_WORD = re.compile(rf"\b{_BE}\b", re.IGNORECASE)
_PP_IRREG = (r"(?:done|made|sent|read|built|kept|held|set|put|run|written|"
             r"shown|given|taken|found|got|gotten|seen|known|thrown|drawn)")
_PASSIVE = re.compile(rf"\b{_BE}\s+(?:\w+ed|{_PP_IRREG})\b", re.IGNORECASE)
_ING_MAIN = re.compile(rf"\b{_BE}\s+\w+ing\b", re.IGNORECASE)
_NOMINAL = re.compile(
    r"\b(?:perform|performs|conduct|conducts|carry out|carries out|"
    r"make use of|makes use of)\b"
    r"|\b\w+(?:tion|ment|ance|ence)s?\s+of\b", re.IGNORECASE)
# Ordinary "of" phrases are fine; only a nominalizing suffix directly before
# "of" counts, which is why "top of the file" passes and "utilization of"
# does not.

# Which categories fail --gate, by slop level. Passive-voice, gerund,
# nominalization, and long-paragraph checks exist as REPORT-ONLY categories
# (the Phase 2 block in check_text) and are deliberately absent from every set
# below: those heuristics are noisy, and a noisy gate is a gate somebody
# switches off.
HARD_BY_SLOP = {
    "strict": {"em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
               "contraction", "semicolon", "long_sentence", "modal_hedge"},
    "flavored": {"em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
                 "modal_hedge"},
    "off": set(),
}

# Categories that can never gate. They inform, so they get their own totals and
# stay out of the headline number: the delta a writer tracks must move only on
# enforceable signal.
REPORT_ONLY = frozenset({
    "passive_voice", "ing_main_verb", "nominalization", "long_paragraph",
    "be_verb",
})

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
    if slop not in HARD_BY_SLOP:
        raise _wp.ProfileError(
            f"unknown slop level {slop!r}; a gate that cannot recognize its "
            "level must refuse rather than silently switch off")
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

    # Phase 2 report-only checks. These heuristics are noisy, so they inform
    # and never gate; the comment above HARD_BY_SLOP is the contract.
    pv = len(_PASSIVE.findall(prose))
    if pv:
        v["passive_voice"] = pv
    ing = len(_ING_MAIN.findall(prose))
    if ing:
        v["ing_main_verb"] = ing
    nom = len(_NOMINAL.findall(low))
    if nom:
        v["nominalization"] = nom
    long_paras = sum(1 for p in paragraphs(prose) if len(sentences(p)) > 6)
    if long_paras:
        v["long_paragraph"] = long_paras

    if profile.get("eprime"):
        be = len(_BE_WORD.findall(prose))
        if be:
            v["be_verb"] = be

    gated = {k: n for k, n in v.items() if k not in REPORT_ONLY}
    informers = {k: n for k, n in v.items() if k in REPORT_ONLY}
    total = sum(gated.values())
    report_total = sum(informers.values())
    per100w = round(total * 100.0 / words, 2) if words else 0.0
    report_per100w = round(report_total * 100.0 / words, 2) if words else 0.0
    hard_cats = HARD_BY_SLOP.get(slop, set())
    hard = sorted(c for c in v if c in hard_cats)

    ease = reading_ease(prose)
    band = profile.get("readability_band") or (0, 100)
    in_band = None if ease is None else bool(band[0] <= ease <= band[1])

    return {
        "words": words, "sentences": len(sents), "violations": v,
        "total": total, "per100w": per100w,
        "report_total": report_total, "report_per100w": report_per100w,
        "em_dash": em, "hard": hard,
        "reading_ease": ease, "in_band": in_band,
    }


def score_file(path: str, profile: dict, text: "str | None" = None) -> dict:
    raw = text if text is not None else Path(path).read_text(
        encoding="utf-8", errors="replace")
    if str(path).endswith(".py"):
        rec = check_text(_ps.prose_of(raw), profile)
        rec["scored"] = "docstrings+comments"
    else:
        rec = check_text(raw, profile)
        rec["scored"] = "text"
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

    if not args.delta and not args.files:
        print("no files given; a gate over nothing proves nothing",
              file=sys.stderr)
        return 2

    def resolve(path: str, text: str) -> str:
        return (args.profile or _wp.declared_profile(text)
                or _wp.profile_for(path))

    try:
        if args.delta:
            old_p, new_p = args.delta
            old_text = Path(old_p).read_text(encoding="utf-8", errors="replace")
            new_text = Path(new_p).read_text(encoding="utf-8", errors="replace")
            prof = _wp.load(resolve(new_p, new_text))
            d = delta(old_text, new_text, prof)
            print(json.dumps(d) if args.as_json
                  else f"delta per100w: {d['old']} -> {d['new']} ({d['delta']:+})")
            if args.gate and check_text(new_text, prof)["hard"]:
                return 1
            return 0

        records, names = [], []
        for f in args.files:
            raw = Path(f).read_text(encoding="utf-8", errors="replace")
            name = resolve(f, raw)
            records.append(score_file(f, _wp.load(name), raw))
            names.append(name)
    except _wp.ProfileError as exc:
        print(f"unknown profile: {exc}", file=sys.stderr)
        return 2

    any_hard = any(r["hard"] for r in records)
    if args.as_json:
        print(json.dumps({"files": records, "does_not_prove": DOES_NOT_PROVE},
                         indent=1))
    else:
        for r, prof_name in zip(records, names):
            print(f"{r['path']}  profile={prof_name} words={r['words']} "
                  f"total={r['total']} per100w={r['per100w']} "
                  f"report_per100w={r['report_per100w']} "
                  f"em_dash={r['em_dash']} hard={','.join(r['hard']) or '-'}")
        print(DOES_NOT_PROVE)
    return 1 if (args.gate and any_hard) else 0


if __name__ == "__main__":
    sys.exit(main())
