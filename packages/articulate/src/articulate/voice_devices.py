"""Rhetorical devices that span sentences and paragraphs.

The line scanner in detector.py reads one line at a time, so a post written as
one short sentence per paragraph passes it clean. This module reads the whole
text as a flat run of sentences and names the shapes that show up when a
writer, or a model, builds a post from a template:

- tells: one-line paragraphs, anaphora and epistrophe runs, fragment runs,
  tricolons, the split antithesis ("It is not X. It is Y."), aphorism lines,
  a closing maxim, numbered escalations, colon drumrolls and stock reveal
  phrases ("This is not a secret.").
- works: a documented anchor (a date, a number, a quote, a source), a turn, a
  question to the reader, a what-if, a sentence from the other side, a named
  opposing view and a first-person judgment.

Every finding carries its line and a short snippet. A tell is a shape, and it
says nothing about who wrote the text: people use all of these. Standard
library only.
"""
import re

from . import corpus_features as cf
from . import detector

STOP_OPENERS = frozenset({"the", "a", "an", "i", "it", "this", "that", "and", "but", "so", "he",
                          "she", "they", "we", "you", "there", "what", "is", "of", "to"})
NEGATION = re.compile(r"(?i)\b(?:not|never|no longer|stopped being|ceased? to be)\b|n't\b")
COPULA_NEG = re.compile(r"(?i)\b(?:is|are|was|were|it's|that's)\s+not\b|\b(?:isn't|aren't|wasn't|weren't)\b"
                        r"|\bstopped being\b")
SUBJECT_COPULA = re.compile(r"(?i)^(?:it|that|this|they|he|she)(?:\s+(?:is|are|was|were)|'s|'re)\b")
ONLY_OPENER = re.compile(r"(?i)^(?:only|just|merely)\b")
HEDGE = re.compile(r"(?i)\b(?:perhaps|possibly|potentially|maybe|arguably|seemingly|presumably"
                   r"|conceivably|somewhat|probably|might|it seems|sort of|kind of)\b")
APHORISM = re.compile(r"(?i)^(?:the|this|that|it|its|what)\b[\w' -]{0,40}?\b(?:is|are|was|were|'s)\b"
                      r"\s+(?:always\s+|never\s+|exactly\s+|just\s+)?[\w' -]{1,40}[.!]$")
BOLD_LINE = re.compile(r"^\s*(?:\*\*|__)[^*_\n]+(?:\*\*|__)\s*$")
ORDINAL = re.compile(r"(?i)^(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
                     r"|finally|lastly)\s*[:,]")
REVEAL = re.compile(
    r"(?i)\b(?:this is not a secret|this isn'?t a secret|it'?s no secret|let'?s just say"
    r"|let'?s (?:stop lying to ourselves|be honest)|sorry to break it to you"
    r"|here'?s the (?:thing|truth|kicker|catch)|the (?:uncomfortable|hard|simple|inconvenient) truth"
    r"|(?:nobody|no one) (?:mentions|mentioned|talks about|tells you)|now ask:|read that again"
    r"|let that sink in|make no mistake|that'?s the whole point)\b")
_W = r"(?!(?:and|or)\b)[a-z][\w'-]+"
TRICOLON = re.compile(rf"(?<!, )\b({_W}(?: {_W}){{0,2}}), ({_W}(?: {_W}){{0,2}}),?"
                      rf" (?:and|or) ((?:(?:the|a|an|no|its|their|his|her|my|our|your) )?{_W}"
                      rf"(?: {_W})?)\b(?!,| [a-z]+,)")
COPULA = re.compile(r"^(?:is|are|was|were|be|been|do|does|did)\b")
ANCHOR = re.compile(r"\b(?:1[89]\d\d|20\d\d)\b|\d[\d,.]*\s*(?:%|percent|per\b|million|billion|bn\b)"
                    r"|\$\d|\b\d{2,}[\d,]*\b|https?://|\(\s*(?:source|see|[A-Z][\w.]+ \d+:\d+)"
                    r"|\b(?:according to|reported|records show|the (?:report|study|paper|filing) )",
                    re.I)
QUOTE = re.compile(r"[\"“][^\"”\s]+\s[^\"”]{2,}[\"”]")
TURN = re.compile(r"(?i)(?:^|[.;:]\s+)(?:yet|still|meanwhile|except|even so|that'?s true"
                  r"|that is true)\b|\bbut\b")
WHAT_IF = re.compile(r"(?i)\bwhat if\b|\bsuppose\b|\bimagine\b|\bpicture (?:a|the|this)\b"
                     r"|\bif (?:you|i|we) (?:were|had|ran|lived)\b|\bsay you\b|\bput yourself\b")
OTHER_SHOES = re.compile(r"(?i)\b(?:from|on) (?:their|his|her|the other) side\b"
                         r"|\bfrom (?:the |a |an )?[\w-]+'s side\b|\bfrom the side of\b"
                         r"|\bin (?:their|his|her|your) shoes\b|\bif i were (?:them|him|her)\b"
                         r"|\bfrom where (?:they|he|she) (?:stands?|sits?)\b|\bhow (?:it|this) looks to\b"
                         r"|\bto (?:them|him|her|a \w+ who)\b[^.?!]{0,60}\b(?:looks?|reads?|feels?|sounds?)\b"
                         r"|\bif you(?:'re| are) (?:a|an|the|one of)\b|\bseen from\b")
COUNTER_VIEW = re.compile(r"(?i)\b(?:says?|said|claims?|argues?|insists?|calls? (?:it|them|this)"
                          r"|the (?:usual|standard|common) (?:line|answer|reading)|the answer is"
                          r"|people (?:say|tell)|one reply)\b")
STANCE = re.compile(r"(?i)\bI(?:'d| would)?(?: still| also| just)? (?:think|argue|disagree|doubt"
                    r"|don'?t buy|don'?t think|believe|say|read|want|care)\b"
                    r"|\bI'?m not (?:convinced|sure that)\b|\bmy (?:view|read)\b")
FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'd|I'll|my|me|mine)\b")

TELL_LABELS = {
    "one-line-paragraphs": "most paragraphs are one sentence",
    "anaphora-run": "three or more sentences open the same way",
    "epistrophe-run": "three or more sentences end the same way",
    "fragment-run": "three or more fragments in a row",
    "tricolon": "a list of three short items for rhythm",
    "split-antithesis": "a negated sentence answered by its mirror (It is not X. It is Y.)",
    "aphorism-line": "a short maxim set alone as a paragraph",
    "closing-maxim": "the post ends on a maxim",
    "numbered-escalation": "First:, Second:, Third: as rhetoric",
    "colon-drumroll": "a colon that sets up a short reveal",
    "reveal-setup": "a stock reveal phrase",
    "hedge": "a hedge word (perhaps, arguably, might)",
}
WORK_LABELS = {
    "anchor": "a documented anchor: a date, a number, a quote or a source",
    "turn": "a turn: the place the argument changes direction",
    "reader-question": "a question the reader has to answer",
    "what-if": "a what-if that changes one fact",
    "other-shoes": "a sentence from the other person's side",
    "counter-view": "the opposing view, named",
    "stance": "a first-person judgment",
}


def sentences(text):
    """Flat (line, paragraph index, sentence) records for every prose sentence."""
    out = []
    for p, block in enumerate(cf.prose_blocks(text.replace("’", "'").replace("‘", "'"))):
        body = block["text"]
        for a, end in cf.sentence_bounds(body):
            s = " ".join(detector.strip_markup(body[a:end]).split())
            if cf.words(s):
                out.append((block["line_start"] + body[:a].count("\n"), p, s))
    return out


def _hit(kind, line, snippet, detail=""):
    return {"id": kind, "line": line, "snippet": snippet[:90], "detail": detail}


def _opener(s, two):
    w = [x.lower() for x in cf.words(s)]
    return " ".join(w[:2]) if two else (w[0] if w else "")


def _runs(sents, key, minimum=3):
    """Maximal runs of consecutive sentences whose key is equal and truthy."""
    runs, i = [], 0
    while i < len(sents):
        k, j = key(sents[i][2]), i + 1
        while k and j < len(sents) and key(sents[j][2]) == k:
            j += 1
        if k and j - i >= minimum:
            runs.append((i, j, k))
        i = j
    return runs


def _anaphora(sents):
    def key(s):
        first = _opener(s, False)
        return _opener(s, True) if first in STOP_OPENERS else first
    return [_hit("anaphora-run", sents[i][0], sents[i][2], f"{j - i} open with '{k}'")
            for i, j, k in _runs(sents, key)]


def _epistrophe(sents):
    def key(s):
        w = [x.lower() for x in cf.words(s)]
        return " ".join(w[-2:]) if len(w) >= 3 else ""
    return [_hit("epistrophe-run", sents[i][0], sents[i][2], f"{j - i} end with '{k}'")
            for i, j, k in _runs(sents, key)]


def _fragments(sents):
    return [_hit("fragment-run", sents[i][0], sents[i][2], f"{j - i} fragments of four words or fewer")
            for i, j, _ in _runs(sents, lambda s: len(cf.words(s)) <= 4 and not s.endswith("?"))]


def _split_antithesis(sents):
    out = []
    for (ln, _, a), (_, _, b) in zip(sents, sents[1:]):
        if not NEGATION.search(a) or NEGATION.search(b):
            continue
        same = len(cf.words(a)) > 1 and _opener(a, True) == _opener(b, True)
        mirror = (bool(COPULA_NEG.search(a)) and bool(SUBJECT_COPULA.match(b))
                  or len(cf.words(b)) <= 8 and bool(ONLY_OPENER.match(b)))
        if same or mirror:
            out.append(_hit("split-antithesis", ln, f"{a} {b}"))
    return out


def _is_maxim(s):
    n = len(cf.words(s))
    return (n <= 12 and not s.endswith("?") and not ANCHOR.search(s) and not QUOTE.search(s)
            and not FIRST_PERSON.search(s) and not REVEAL.search(s) and bool(APHORISM.match(s)))


def _paragraph_shapes(sents):
    """One-line paragraph share, aphorism lines and the closing maxim."""
    by_para = {}
    for rec in sents:
        by_para.setdefault(rec[1], []).append(rec)
    paras = [by_para[k] for k in sorted(by_para)]
    single = [p for p in paras if len(p) == 1]
    share = round(len(single) / len(paras), 3) if paras else 0.0
    out = []
    if len(paras) >= 6 and share >= 0.6:
        out.append(_hit("one-line-paragraphs", paras[0][0][0], paras[0][0][2],
                        f"{len(single)} of {len(paras)} paragraphs"))
    for p in single[:-1] if paras and len(paras[-1]) == 1 else single:
        if _is_maxim(p[0][2]):
            out.append(_hit("aphorism-line", p[0][0], p[0][2]))
    if paras and _is_maxim(paras[-1][-1][2]):
        out.append(_hit("closing-maxim", paras[-1][-1][0], paras[-1][-1][2]))
    return out, share, len(paras)


def _bold_lines(text):
    return [_hit("aphorism-line", n, line.strip()) for n, line in enumerate(text.splitlines(), 1)
            if BOLD_LINE.match(line) and len(cf.words(line)) <= 12]


def _balanced_triad(s):
    """Three list items of near-equal length, tried from each word so the first item stays short."""
    for start in (m.start() for m in re.finditer(r"\b\w", s)):
        m = TRICOLON.match(s, start)
        if not m or start and s[start - 1] not in " (":
            continue
        sizes = [len(g.split()) for g in m.groups()]
        if max(sizes) - min(sizes) <= 1 and not any(COPULA.match(g) for g in m.groups()[1:]):
            return m.group(0)
    return ""


def _repeated_triad(s):
    """A word repeated in three comma-separated parts (enough times, in enough places...)."""
    parts = [set(w.lower() for w in cf.words(p)) - STOP_OPENERS for p in re.split(r",|\band\b|\bor\b", s)]
    for a, b, c in zip(parts, parts[1:], parts[2:]):
        shared = a & b & c
        if shared:
            return "repeated '" + sorted(shared)[0] + "'"
    return ""


def _sentence_shapes(sents):
    out = []
    ordinals = [r for r in sents if ORDINAL.match(r[2])]
    if len(ordinals) >= 3:
        out.append(_hit("numbered-escalation", ordinals[0][0], ordinals[0][2],
                        f"{len(ordinals)} ordinal openers"))
    for (ln, p, a), (_, q, b) in zip(sents, sents[1:]):
        if a.endswith(":") and q != p and len(cf.words(b)) <= 8:
            out.append(_hit("colon-drumroll", ln, f"{a} {b}"))
    for ln, _, s in sents:
        m = REVEAL.search(s)
        if m:
            out.append(_hit("reveal-setup", ln, s, m.group(0)))
        triad = _balanced_triad(s) or _repeated_triad(s)
        if triad:
            out.append(_hit("tricolon", ln, s, triad))
    return out


WORK_RULES = (("anchor", lambda s: ANCHOR.search(s) or QUOTE.search(s)),
              ("turn", TURN.search), ("reader-question", lambda s: s.endswith("?")),
              ("what-if", WHAT_IF.search), ("other-shoes", OTHER_SHOES.search),
              ("counter-view", COUNTER_VIEW.search), ("stance", STANCE.search))


def _works(sents):
    return [_hit(kind, ln, s) for ln, _, s in sents for kind, rule in WORK_RULES if rule(s)]


def analyze(text):
    """Tells and working devices in text, with counts by id."""
    sents = sentences(text)
    shapes, share, n_paras = _paragraph_shapes(sents)
    tells = (shapes + _bold_lines(text) + _anaphora(sents) + _epistrophe(sents) + _fragments(sents)
             + _split_antithesis(sents) + _sentence_shapes(sents))
    tells += [_hit("hedge", ln, s, m.group(0)) for ln, _, s in sents for m in HEDGE.finditer(s)]
    tells.sort(key=lambda h: (h["line"], h["id"]))
    works = _works(sents)
    counts = {k: 0 for k in list(TELL_LABELS) + list(WORK_LABELS)}
    for h in tells + works:
        counts[h["id"]] += 1
    first_anchor = next((i for i, (_, _, s) in enumerate(sents)
                         if ANCHOR.search(s) or QUOTE.search(s)), None)
    return {"sentences": len(sents), "paragraphs": n_paras, "one_line_share": share,
            "first_person": sum(len(FIRST_PERSON.findall(detector.mask_quotes(s))) for _, _, s in sents),
            "anchor_sentence": first_anchor, "tells": tells, "works": works, "counts": counts}
