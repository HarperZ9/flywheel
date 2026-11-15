"""The author's register, measured, so a rewrite cannot flatten it in silence.

A voice is more than its sentence lengths. The author's own register, from his
stated stance and from the author's own description of their process, holds
features a neutral rewrite tends to strip:

  imagery         concrete, visual words: things, places, bodies, weather
  forward-motion  prediction and motion framing: next, ahead, by the time,
                  about to, see it coming, lay down the path as I walk
  idea-runs       long sentences that chain three or more ideas, kept as runs
  observer        first-person watching: I saw, I watched, here's what I saw
  first-person    I, me, my
  questions       questions put to the reader
  reader          the reader addressed as you
  contrarian      a view named so it can be pushed against, or a turn on it
  jaded           seen-it-before words: again, of course, same trick
  wonder          plain amazement: wild, strange, beautiful
  defensive       a guard put up before the concession
  profanity       the plain word where it fits
  analogy         an analogy that carries structure across: mapped parts or a
                  relation (articulate.analogy); flattening it to a stock
                  comparison, or dropping it, counts as a loss
  symbol          symbolic messaging: an object made to stand for an idea
                  (stands for, a symbol of, the mirror, the mask, the scale)
  confrontation   direct address that holds the reader to their own
                  contradiction (you say ... but you, ask yourself, so do you)

`measure(text)` counts each feature with the lines it sits on. `flattening(
before, after)` names every feature the rewrite lost (present before, under
half as often after) and a run of ideas turned into a list. These are voice,
and the profile protects them. `guard` attaches that report to an edit result;
voice apply and every edit planned under the author-voice profile keep the
original text when the rewrite lost a feature. Voice apply takes
accept_register_change=True from an author who wants the change anyway.

The counts read surface words. They measure fit to a register and say nothing
about whether a claim is true. Standard library only.
"""
from __future__ import annotations

import re

from . import analogy as A
from . import devices_lex as X
from . import imagery_lex as L

SCHEMA = "articulate/voice-register/v1"
SCOPE = ("Counts register features by surface words. It reports what a rewrite kept and "
         "lost; the author decides what stays.")

_RX = {
    "forward-motion": r"\b(?:next|ahead|by the time|about to|going to|see (?:it|this|that) coming|"
                      r"before (?:it|they|you|anyone|the)|already know|forward|predict\w*|"
                      r"in (?:a|ten|five|two) (?:seconds?|minutes?)|as I walk|lay down the path)\b",
    "observer": r"\bI (?:saw|see|watched|watch|noticed|notice|looked|heard|counted|caught|spotted)\b|"
                r"\bhere'?s what I (?:saw|see|found)\b",
    "first-person": r"\b(?:I|I'm|I've|I'd|I'll|me|my|mine)\b",
    "reader": r"\b(?:you|your|you're|yours)\b",
    "contrarian": r"\b(?:everyone|everybody|they) (?:says?|thinks?|tells? you|will tell you)\b|"
                  r"\b(?:sure|fine|okay|right)[,.]|\bfunny how\b|\bexcept\b|\bwrong\b|\bnope\b|"
                  r"\bthe (?:story|line|pitch) (?:goes|is)\b",
    "jaded": r"\b(?:again|of course|seen (?:it|this|that) before|same (?:trick|old|story|move)|"
             r"every (?:single )?time|as usual|naturally|yeah,? right|surprise,? surprise)\b",
    "wonder": r"\b(?:wild|amazing|beautiful|strange|weird|incredible|wow|stunning|gorgeous|"
              r"blows? my mind|still gets me)\b",
    "defensive": r"\b(?:don'?t look at me|look,|I know,|yeah,? I|so what|before you (?:say|ask)|"
                 r"I'?m not (?:saying|pretending))",
    "profanity": r"\b(?:damn|hell|shit\w*|fuck\w*|crap|bullshit|ass)\b",
    "symbol": r"\b(?:stands? for|symboli[sz]e[sd]?|a symbol of|the emblem of|"
              r"(?:the|a|your|our) (?:mirror|mask|blindfold|mast|scales?|chain|cage|crown|"
              r"white feather|golem|janus|caduceus) (?:of|for|we|you|they|that|everyone|"
              r"nobody|every)\b)",
    "confrontation": r"\byou (?:say|said|claim|tell yourself|swear|call it|preach)\b[^.?!]{0,120}?"
                     r"\b(?:but|yet|and then|while) you\b|\bask yourself\b|\bbe honest\b|"
                     r"\badmit it\b|\bso do you\b|\byou do (?:it|this|that) too\b|"
                     r"\byou(?:'d| would) do the same\b|\blook in the mirror\b|\bsame as you\b",
}
_COMPILED = {k: re.compile(v, re.I if k not in ("first-person", "observer") else 0)
             for k, v in _RX.items()}
_RUN_JOINT = re.compile(r"(?i)\s(?:and|then|so|while|until)\s|;|,\s(?:which|and then)\s")
_LIST = re.compile(r"(?m)^\s*(?:[-*+]|\d{1,3}[.)])\s+\S")
_SENT = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")

FEATURES = ("imagery", "forward-motion", "idea-runs", "observer", "first-person", "questions",
            "reader", "contrarian", "jaded", "wonder", "defensive", "profanity", "analogy",
            "symbol", "confrontation")


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def measure(text):
    """{'schema', 'words', 'counts', 'lines', 'list_items'} for one text."""
    text = (text or "").replace("’", "'")
    counts = {k: 0 for k in FEATURES}
    lines = {k: [] for k in FEATURES}
    for key, rx in _COMPILED.items():
        for m in rx.finditer(text):
            counts[key] += 1
            lines[key].append(_line(text, m.start()))
    for hit in A.find(text):
        if hit["verdict"] == "carries":
            counts["analogy"] += 1
            lines["analogy"].append(_line(text, hit["start"]))
    for m in _SENT.finditer(text):
        s = m.group(0)
        ws = X.words(s)
        n = len(L.image_words(ws))
        if n:
            counts["imagery"] += n
            lines["imagery"].append(_line(text, m.start()))
        if s.rstrip().endswith("?"):
            counts["questions"] += 1
            lines["questions"].append(_line(text, m.start()))
        if len(ws) >= 25 and len(_RUN_JOINT.findall(s)) >= 3:
            counts["idea-runs"] += 1
            lines["idea-runs"].append(_line(text, m.start()))
    return {"schema": SCHEMA, "words": len(X.words(text)), "counts": counts,
            "lines": {k: sorted(set(v))[:12] for k, v in lines.items()},
            "list_items": len(_LIST.findall(text))}


def flattening(before, after):
    """What a rewrite of the author's own text kept and lost of the register."""
    b, a = measure(before), measure(after)
    rows, lost = [], []
    for key in FEATURES:
        nb, na = b["counts"][key], a["counts"][key]
        status = "absent" if nb == 0 else ("lost" if na * 2 < nb else "kept")
        rows.append({"feature": key, "before": nb, "after": na, "status": status,
                     "lines_before": b["lines"][key]})
        if status == "lost":
            lost.append(key)
    listed = (a["list_items"] - b["list_items"] >= 3
              and a["counts"]["idea-runs"] < b["counts"]["idea-runs"])
    if listed:
        lost.append("runs-to-list")
    return {"schema": SCHEMA, "flattened": bool(lost), "lost": lost, "features": rows,
            "list_items_before": b["list_items"], "list_items_after": a["list_items"],
            "scope": SCOPE}


def guard(original, out, rebuild, accept=False):
    """Attach the register report to an edit result. When the edit lost a feature
    and the author has not accepted that, return rebuild(reason): the result with
    the original text kept and the reason listed with the refusals."""
    report = flattening(original, out["text"])
    if report["flattened"] and not accept and out["text"] != original:
        reason = {"paragraph": None,
                  "reasons": ["the rewrite flattened the author's register: lost "
                              + ", ".join(report["lost"])]}
        out = rebuild(reason)
    out["register"] = report
    return out
