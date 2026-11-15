"""The dialogue profile: shapes that make a spoken line sound written.

Prose rules do not fit fiction dialogue. People repeat themselves, break off,
drop words and talk in fragments, and none of that is flagged here. What is
flagged is the shape a model reaches for when it writes a character: the
balanced antithesis, the epigram, the character who states the theme, the
line that ends on a zinger, and a line thick with abstract nouns.

check_line(text, theme_words) returns a list of findings. Each finding is
{"check", "label", "weight", "excerpt"}. Weights add into a line score.
"""
import re

from . import detector
from .dialogue_lexicon import (COPULA, FUNCTION, NEGATION, PRONOUNS, abstract_nouns, content_words,
                               is_abstract, sentences, words)

WEIGHTS = {"antithesis": 3, "contrast-pair": 3, "epigram-semicolon": 3,
           "epigram-definition": 3, "epigram-maxim": 2, "epigram-here": 3, "theme-statement": 2,
           "closing-zinger": 2, "abstract-density": 1}
EPIGRAM_CHECKS = ("epigram-semicolon", "epigram-definition", "epigram-maxim", "epigram-here")

# The prose detector's antithesis devices that hold in speech. "not X but Y" alone
# fires on ordinary talk ("not now, but soon") and is left to the calibration notes.
_ANTITHESIS_LABELS = {"it's not just X, it's Y", "is not X, it is Y", "not only ... but (also)",
                      "never ... always", "this isn't about X, it's about Y"}
_ANTITHESIS = [(label, rx) for cat, label, rx in detector.HIGH + detector.MEDIUM
               if label in _ANTITHESIS_LABELS]

_EVALUATIVE = frozenset("""
wicked good evil cheap dear right wrong true false honest decent cruel kind proud brave
sweet bitter easy hard simple safe dangerous holy sacred fair foul pure plain clever stupid
foolish wise cowardly dull tedious charming vulgar useless worthless fatal
""".split())
_FREQUENCY = re.compile(r"\b(?:always|never|ever|rarely|seldom|usually|often|nowadays)\b", re.I)
_PAST = re.compile(r"\b(?:was|were|did|had|went|said|saw|came|got|told)\b", re.I)
_ONE = re.compile(r"^(?:when\s+|if\s+)?one\s+(?:is|can|must|should|has|does|never|always|"
                  r"may|\w+s)\b", re.I)
_CLASS_OPEN = re.compile(r"^(?:all|no|every|none of|nobody|no one|everybody|everyone|people|"
                         r"men|women|folk)\b", re.I)
_BARE_PLURAL = re.compile(r"^([A-Za-z]+s)\s+(?:are|do|have|can|never|always|rarely|seldom|"
                          r"usually|often|make|become)\b")
_SUPERLATIVE = re.compile(r"^the\s+(?:only|very|whole|real|true|best|worst|first)\b[^,;]*\bis\b",
                          re.I)
_PERFECT = re.compile(r"(?:['’]s|\bhas|\bhave|['’]ve)\s+(?:ever\s+|never\s+|not\s+)?"
                      r"\w+(?:ed|en|wn|ung|ought)\b", re.I)
_DEF_SUBJECT = re.compile(r"^(?:the\s+)?([A-Za-z]+)\s+(?:is|are|was|were)\s+"
                          r"(?:a\s+|an\s+|the\s+|only\s+|just\s+|always\s+|never\s+)?"
                          r"([A-Za-z]+)", re.I)
_PRONOUN_IS = re.compile(r"^(?:i\s+am|i['’]m|you\s+are|you['’]re|we\s+are|"
                         r"we['’]re|he\s+is|she\s+is|it\s+is|they\s+are|that\s+is)\s+"
                         r"(?:only\s+|just\s+|all\s+)?([A-Za-z]+)[.!]?$", re.I)
_PLACE_OPEN = re.compile(r"^(?:in|up|out|over|back|where|on|at)\b", re.I)
_HERE_OPEN = re.compile(r"^(?:and\s+|but\s+)?(?:here|down here|up here|out here|in here)\b",
                        re.I)
_GNOMIC_OPEN = re.compile(
    r"^(?:a man|a woman|a person|a body|people|everyone|everybody|nobody|no one|no man|"
    r"men|women|folk|the world|a town|you can['’]?t|you never|you always|"
    r"there['’]s no|there is no|always|never)\b", re.I)
_DEIXIS = re.compile(r"\b(?:tonight|today|yesterday|last night|this morning|now|here|"
                     r"this|these|that one|those)\b|\d", re.I)


def _excerpt(s, n=90):
    s = s.strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def _definition(sentence, proper):
    """'Wicked is cheap.' 'Truth is a tide.' 'I am arithmetic.' Short only."""
    ws = words(sentence)
    if not 2 <= len(ws) <= 8:
        return False
    s = sentence.strip().rstrip(".!?\"'”")
    m = _PRONOUN_IS.match(s)
    if m:
        return is_abstract(m.group(1)) and m.group(1).lower() not in PRONOUNS
    m = _DEF_SUBJECT.match(s)
    if not m:
        return False
    subj, pred = m.group(1), m.group(2)
    if subj.lower() in PRONOUNS or subj in proper or subj.lower() == pred.lower():
        return False              # "Glass is glass." repeats; plain speech does that
    return is_abstract(subj) or subj.lower() in _EVALUATIVE


def _maxim(sentence, proper):
    """A general rule stated as fact: 'One should never X.' 'Young men are
    useless.' 'No man is ever Y.' 'The only safe name is Z.' Present tense,
    no time or place pointed at, twelve words at most."""
    ws = words(sentence)
    s = sentence.strip()
    if not 3 <= len(ws) <= 12 or _DEIXIS.search(s) or _PAST.search(s) or "?" in s:
        return False
    if _PERFECT.search(s):
        return False              # "Nobody's ever measured": an event, not a rule
    if _SUPERLATIVE.match(s) or _ONE.match(s):
        return True
    rule_word = bool(_FREQUENCY.search(s)) or any(w.lower() in _EVALUATIVE for w in ws[-2:])
    if _CLASS_OPEN.match(s) and COPULA.search(s):
        return rule_word
    m = _BARE_PLURAL.match(s)
    if m and m.group(1) not in proper and m.group(1).lower() not in FUNCTION:
        return rule_word or bool(abstract_nouns(s))
    return False


def _semicolon(sentence, proper):
    if ";" not in sentence:
        return False
    halves = [h.strip() for h in sentence.split(";")]
    for a, b in zip(halves, halves[1:]):
        wa, wb = len(words(a)), len(words(b))
        if not (2 <= wa <= 8 and 2 <= wb <= 8) or max(wa, wb) > 2 * min(wa, wb):
            continue
        neg_flip = bool(NEGATION.search(a)) != bool(NEGATION.search(b))
        shared = content_words(a) & content_words(b)
        if (neg_flip and shared) or any(_definition(h, proper) or _maxim(h, proper)
                                        for h in (a, b)):
            return True
    return False


def _here_comparison(text):
    segs = [s.strip() for s in re.split(r"[.;!?]|,\s+(?=(?:but\s+)?here\b)", text, flags=re.I)
            if s.strip()]
    for i, seg in enumerate(segs):
        if (_PLACE_OPEN.match(seg) and len(words(seg)) >= 3
                and not re.search(r"\bhere\b", seg, re.I)):   # the elsewhere, then here
            if any(_HERE_OPEN.match(later) for later in segs[i + 1:]):
                return True
    return False


def _shared(a, b, proper):
    def keep(t):
        return {w.lower() for w in words(t)[1:] if len(w) >= 3 and w.lower() not in FUNCTION
                and w not in proper and not NEGATION.match(w)}
    return keep(a) & keep(b)


def _contrast(sents, proper):
    """Adjacent short sentences with the same opening word and a shared word, one
    negated and one not: 'We do not say it broke. We say it was opened.'"""
    for a, b in zip(sents, sents[1:]):
        wa, wb = words(a), words(b)
        if not (2 <= len(wa) <= 10 and 2 <= len(wb) <= 10):
            continue
        if wa[0].lower() != wb[0].lower():
            continue
        if bool(NEGATION.search(a)) == bool(NEGATION.search(b)):
            continue
        if _shared(a, b, proper):
            return a + " " + b
    return None


def _gnomic(sentence, proper):
    s = sentence.strip()
    if _DEIXIS.search(s) or _PAST.search(s) or _PERFECT.search(s) or len(words(s)) < 4:
        return False              # an event that happened is not a rule about the world
    return bool(_GNOMIC_OPEN.match(s)) or _definition(s, proper) or _maxim(s, proper)


def _negated_present(s):
    """'The Board is not, strictly, a you.' A short present-tense denial; an event
    in the past ('There was nothing below.') is reporting, not a zinger."""
    return (len(words(s)) >= 3 and bool(NEGATION.search(s)) and bool(COPULA.search(s))
            and not (_DEIXIS.search(s) or _PAST.search(s) or _PERFECT.search(s)))


def check_line(text, theme_words=(), proper=frozenset()):
    """Findings for one spoken line. `proper` holds names, so 'Mother is dark' is
    a statement about a lamp and not a definition of an abstraction."""
    found = []
    sents = sentences(text) or [text]

    def add(check, label, excerpt):
        found.append({"check": check, "label": label, "weight": WEIGHTS[check],
                      "excerpt": _excerpt(excerpt)})

    for label, rx in _ANTITHESIS:
        m = rx.search(text)
        if m:
            add("antithesis", label, m.group(0))
            break
    pair = _contrast(sents, proper)
    if pair:
        add("contrast-pair", "contrast pair (one affirms, the next negates)", pair)
    for s in sents:
        if _semicolon(s, proper):
            add("epigram-semicolon", "two short clauses balanced on a semicolon", s)
            break
    for s in sents:
        if ";" not in s and _definition(s, proper):
            add("epigram-definition", "an abstraction defined in a few words", s)
            break
    for s in sents:
        if ";" not in s and not _definition(s, proper) and _maxim(s, proper):
            add("epigram-maxim", "a general rule stated as fact", s)
            break
    if _here_comparison(text):
        add("epigram-here", "'In A ... here ...' comparison", text)
    themes = {t.lower() for t in theme_words}
    if themes:
        for s in sents:
            hits = {w.lower() for w in words(s)} & themes
            if hits and (_gnomic(s, proper) or len(hits) >= 2):
                add("theme-statement", "states the theme: " + ", ".join(sorted(hits)), s)
                break
    if len(sents) >= 2:
        last = sents[-1]
        n_last = len(words(last))
        prior = [len(words(s)) for s in sents[:-1]]
        if (n_last <= 7 and sum(prior) / len(prior) >= 1.5 * n_last
                and (_gnomic(last, proper) or abstract_nouns(last)
                     or _negated_present(last))):
            add("closing-zinger", "ends on a short aphoristic sentence", last)
    ab = abstract_nouns(text)
    n = len(words(text))
    if len(ab) >= 2 and n and len(ab) / n >= 0.12:
        add("abstract-density", f"{len(ab)} abstract nouns in {n} words", ", ".join(ab))
    return found


def proper_nouns(lines):
    """Capitalised words that appear mid-sentence, plus every speaker name: the
    names a script uses, so they are not read as abstractions."""
    names = set()
    for rec in lines:
        names.update(p.capitalize() for p in rec["speaker"].split())
        for s in sentences(rec["text"]):
            for w in words(s)[1:]:
                if w[0].isupper() and w.lower() not in PRONOUNS and w != "I":
                    names.add(w)
    return frozenset(names)
