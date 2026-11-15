"""Single-sentence detectors for the structure rule pack: a sentence that does
a stock job in its paragraph.

  pin      a paragraph's first sentence that only announces the paragraph.
           Measured: it opens a paragraph, has at most PIN_WORDS words, and
           either carries a pointing phrase ("here is", "the following",
           "each of them", "two things") or is a label of at most LABEL_WORDS
           words with a possessive or one-word complement ("The cause is
           mine."). The label form also needs two sentences after it.
  pointer  a sentence whose whole predicate judges another sentence or the
           text before it: "That matters.", "That agrees with ...", "That is
           the silo.", "His last sentence is the useful part."
  landing  a paragraph's last sentence that hands the next step back ("... is
           up to you.", "... is yours to write.") or closes a paragraph of
           four or more sentences with one short clause. The same hand-back
           earlier in a paragraph is reported one tier lower.

A list item is read as a short paragraph by these three rules, so a hand-back
that closes a bullet is a landing sentence, and a one-sentence item counts as
its own close.

Each phrase list is a closed list, so a paraphrase gets past it. English only.
Standard library only.
"""
from __future__ import annotations

import re

from . import structure_text as T
from .wordlists import FUNCTION_WORDS

PIN_WORDS = 8
LABEL_WORDS = 5
POINTER_WORDS = 12
BEAT_WORDS = 6
LANDING_WORDS = 16
VERDICT_WORDS = 12
VERDICT_PARAGRAPH = 4
HANDOFF_TAIL = 4           # words allowed after the hand-back phrase in a long sentence

_COUNT = r"(?:a|one|two|three|four|five|six|several|some|a few|a couple of)"
_THING = (r"(?:things?|points?|notes?|caveats?|problems?|reasons?|options?|parts?|steps?"
          r"|questions?|issues?|changes?|findings?|details?|limits?)")
_PIN_CUE = re.compile(
    r"(?i)^here(?:'s|’s| is| are)\b|\bthe following\b|\bas follows\b"
    r"|\beach of (?:them|these|those)\b|^(?:this|that) is (?:where|what|how|why)\b"
    rf"|^{_COUNT} (?:\w+ )?{_THING}\b"
    r"|^(?:the|my|a) (?:short|long|plain|honest|quick) (?:version|answer|story)\b")
_PIN_LABEL = re.compile(
    r"(?i)^(?:the|my|your|our|its|that|this) (?:[\w'’-]+ ){1,2}(?:is|are|was|were) "
    r"(?:[\w'’-]+ ?){1,2}\.$")
_PLAIN_ANSWER = frozenset({"yes", "no", "not"})

_VERBS = (r"agrees|matches|fits|squares|tallies|confirms|supports|settles|explains"
          r"|accounts for|is consistent with|is in line with|lines up with")
_META = (r"sentence|line|paragraph|point|part|question|message|reply|email|section|clause"
         r"|remark|answer|bit|half|piece|item|word|phrase|detail|caveat|claim")
_ORDER = r"first|last|next|final|second|third|opening|closing|other|main|one"
_VALUE = (r"useful|important|key|interesting|relevant|telling|real|main|hard|operative"
          r"|critical|crucial|best|worst|weak|strong|good|bad|right|wrong|fair|central")
_POINTER = (
    ("judge", POINTER_WORDS, re.compile(rf"(?i)^(?:that|this) (?:{_VERBS})\b")),
    ("judge", 3, re.compile(r"(?i)^(?:that|this) [a-z]+s(?: [a-z]+)?\.$")),
    ("meta", POINTER_WORDS, re.compile(
        rf"(?i)^(?:his|her|their|your|my|its|the|that|this) (?:(?:{_ORDER}) )?(?:{_META}) "
        rf"(?:is|was) (?:the |a )?(?:[\w-]+ )?(?:{_VALUE})\b")),
    ("beat", BEAT_WORDS, re.compile(
        r"(?i)^(?:that|this)(?:'s|’s| is| was) (?:the|a|an|what|why|how|where)\b")),
)
_HANDOFF = re.compile(
    r"(?i)\b(?:is|are|was|stays?|remains?) (?:up to (?:you|him|her|them)|yours\b|theirs\b"
    r"|hers\b|his to\b)|\byours to \w+"
    r"|\b(?:is|are|was|stays?|remains?|it['’]s|that['’]s) (?:your|his|her|their) "
    r"(?:call|decision|move)\b|\b(?:your|his|her|their) (?:call|decision|move)[.:]?$"
    r"|\bfor (?:you|him|her|them) to (?:decide|rewrite|approve|judge|pick|choose|say"
    r"|answer|settle|keep|cut|correct)\b|\byou decide\b|\bsay the word\b")


def _content(words):
    return [w for w in words if w.lower() not in FUNCTION_WORDS]


def _is_label(sent):
    words = sent["words"]
    if len(words) > LABEL_WORDS or sent["para"] < 3 or not _PIN_LABEL.match(sent["text"]):
        return False
    return (len(_content(words)) <= 2 and words[-1].lower() not in _PLAIN_ANSWER
            and not any(c.isdigit() for c in sent["text"]))


def pin(unit, text, make):
    found = {"HIGH": [], "MEDIUM": []}
    for sent in unit:
        if not sent["first"] or len(sent["words"]) > PIN_WORDS:
            continue
        colon = sent["text"].endswith(":")
        if _PIN_CUE.search(sent["text"]) and (sent["para"] >= 2 or colon):
            label = ("the paragraph opens by announcing itself; "
                     "start with the content this sentence points at")
            found["HIGH"].append(T.record(make, text, sent, sent, "structure-pin", label, "cue"))
        elif _is_label(sent):
            label = ("the paragraph opens with a short label; "
                     "fold the label into the sentence that carries the content")
            found["MEDIUM"].append(T.record(make, text, sent, sent,
                                            "structure-pin", label, "label"))
    return found


def pointer(unit, text, make):
    found = {"HIGH": [], "MEDIUM": []}
    for sent in unit:
        body = T._LEAD.sub("", T._QUOTED.sub("Q", sent["text"]))   # a quoted line is a mention
        for variant, limit, rx in _POINTER:
            if len(sent["words"]) <= limit and rx.match(body):
                label = {"judge": "the sentence only rates the text before it; "
                                  "state the fact it rests on",
                         "meta": "the sentence points at another sentence and rates it; "
                                 "say what that sentence says",
                         "beat": "a short beat that labels the point before it; "
                                 "cut it or make the point in the sentence itself"}[variant]
                if variant == "beat" and sent.get("item") and sent["first"]:
                    break                  # an item that opens "This is the ..." is content
                tier = "MEDIUM" if variant == "beat" else "HIGH"
                found[tier].append(T.record(make, text, sent, sent,
                                            "structure-pointer", label, variant))
                break
    return found


def _one_clause(sent):
    low = {w.lower() for w in sent["words"]}
    return ("," not in sent["text"] and ";" not in sent["text"]
            and not low & (T.SUBORDINATORS | T.COORDINATORS))


def _hands_back(body, words):
    """True when a sentence carries a hand-back phrase and is short, or is
    long and ends within HANDOFF_TAIL words of the phrase."""
    last = None
    for last in _HANDOFF.finditer(body):
        pass
    if last is None:
        return False
    return len(words) <= LANDING_WORDS or len(T.WORD.findall(body[last.end():])) <= HANDOFF_TAIL


def landing(unit, text, make):
    found = {"HIGH": [], "MEDIUM": []}
    for k, sent in enumerate(unit):
        closes = sent["last"] and (sent["para"] >= 2 or sent.get("item")
                                   or k == len(unit) - 1 and len(unit) >= 2)
        body = sent["text"].rstrip("\"')]”’*_")
        n = len(sent["words"])
        said = T._QUOTED.sub("Q", sent["text"])            # a quoted hand-back is a mention
        if body.endswith((".", ":")) and _hands_back(said, sent["words"]):
            if closes:
                label = ("the paragraph ends by handing the next step back; "
                         "say what you need from the reader, or stop one sentence earlier")
                found["HIGH"].append(T.record(make, text, sent, sent,
                                              "structure-landing", label, "handoff"))
            else:
                label = ("the sentence hands the next step back; "
                         "say once what you need from the reader")
                found["MEDIUM"].append(T.record(make, text, sent, sent,
                                                "structure-landing", label, "handback"))
        elif not closes or not body.endswith("."):
            continue
        elif sent["para"] >= VERDICT_PARAGRAPH and n <= VERDICT_WORDS and _one_clause(sent):
            label = ("the paragraph ends on a short one-clause closer; "
                     "join it to the sentence it restates or cut it")
            found["MEDIUM"].append(T.record(make, text, sent, sent,
                                            "structure-landing", label, "closer"))
    return found


def fingerprint():
    parts = ["MOVES|%s|%s|%s|%s|%s|%s|%s|%s" % (PIN_WORDS, LABEL_WORDS, POINTER_WORDS, BEAT_WORDS,
                                               LANDING_WORDS, VERDICT_WORDS, VERDICT_PARAGRAPH,
                                               HANDOFF_TAIL),
             _PIN_CUE.pattern, _PIN_LABEL.pattern, _HANDOFF.pattern, repr(sorted(_PLAIN_ANSWER))]
    return parts + ["%s|%s|%s" % (v, n, rx.pattern) for v, n, rx in _POINTER]
