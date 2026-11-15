"""Run detectors for the structure rule pack: shapes that need two or more
sentences side by side.

  anaphora   consecutive sentences that open with the same word. An article
             opener counts only when the second word repeats too. Exactly
             three sentences that open on one personal pronoun report at
             MEDIUM: a pronoun subject is how English keeps talking about one
             thing, and human prose does it far more often than a model's
             replies did (docs/structure-rules.md has the counts).
  parallel   three sentences within four that share a syntactic frame. The
             frame is a token-shape signature (structure_text.shape): two
             short sentences match when their signatures are equal, and two
             longer ones when the signatures are within two tokens in length
             and at least FRAME_RATIO alike. A second frame, the label
             sentence, is a subject followed by is/are/was/were and a/an/the.
  triad      exactly three sentences in a row that share an opener or a frame,
             and a three-item list of short phrases inside one sentence. A
             pronoun opener alone makes no triad; the three need one frame.
  parataxis  three or more short statements in a row with no linking word at
             the start of any of them, and a very short statement in a
             paragraph where no sentence links to the one before it.

Every threshold is a constant in this file and enters the pack fingerprint.
Standard library only.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from . import structure_text as T

ARTICLES = frozenset({"a", "an", "the"})
PRONOUN_OPENERS = frozenset({"i", "we", "you", "he", "she", "it", "they"})
FRAME_RATIO = 0.8          # likeness of two long shape signatures
FRAME_SHORT = 5            # signatures this short must be equal
FRAME_WINDOW = 4           # three matching sentences within this many
SHORT_WORDS = 12           # a short statement, for a paratactic run
RUN_MIN = 3                # sentences in a paratactic run
STUB_WORDS = 6             # a very short statement
STUB_PARAGRAPH = 4         # sentences in the paragraph around a stub
_COPULA = frozenset({"is", "are", "was", "were"})
_ITEM = r"(?!(?:and|or)\b)[A-Za-z][\w'’-]*(?: (?!(?:and|or)\b)[A-Za-z][\w'’-]*){0,3}"
_TRIAD = re.compile(rf"(?<![,;] )\b({_ITEM}), ({_ITEM}), (?:and|or) ({_ITEM})(?=[.;:!?)]|$)")


def _key(sent):
    """The opening word a run is counted on, or None for a sentence with none."""
    words = T.opener(sent["text"], 2)
    if not words:
        return None
    return words if words[0] in ARTICLES else words[:1]


def opener_runs(unit):
    """(start, stop, key) for each maximal run of two or more sentences that
    share an opener, as indexes into the unit."""
    out, i = [], 0
    while i < len(unit):
        key, j = _key(unit[i]), i + 1
        while key and j < len(unit) and _key(unit[j]) == key:
            j += 1
        if key and j - i >= 2 and len(key) == (2 if key[0] in ARTICLES else 1):
            out.append((i, j, key))
        i = j
    return out


def anaphora(unit, text, make):
    found = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for i, j, key in opener_runs(unit):
        n, word = j - i, " ".join(key)
        if n == 3 and key[0] in PRONOUN_OPENERS:
            label = (f"3 sentences in a row open with '{word}'; "
                     "join two of them or vary one opening")
            found["MEDIUM"].append(T.record(make, text, unit[i], unit[j - 1],
                                            "structure-anaphora", label, "pronoun-run"))
        elif n >= 3:
            label = (f"{n} sentences in a row open with '{word}'; "
                     "vary the openings or join the sentences")
            found["HIGH"].append(T.record(make, text, unit[i], unit[j - 1],
                                          "structure-anaphora", label, "run"))
        else:
            label = f"2 sentences in a row open with '{word}'; vary one opening"
            found["LOW"].append(T.record(make, text, unit[i], unit[j - 1],
                                         "structure-anaphora", label, "pair"))
    return found


_CONTENT = frozenset({"_", "s", "ed", "ing", "ly"})


def _skeleton(shape):
    """A signature with every content word reduced to one blank."""
    return tuple("_" if tok in _CONTENT else tok for tok in shape)


def same_frame(a, b):
    """True when two shape signatures are one frame with other content words.
    Short signatures must have equal skeletons. Longer ones must open on the
    same token, be within two tokens in length and be FRAME_RATIO alike."""
    if min(len(a), len(b)) < 3:
        return False
    if min(len(a), len(b)) <= FRAME_SHORT:
        return _skeleton(a) == _skeleton(b)
    if abs(len(a) - len(b)) > 2 or a[0] != b[0]:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= FRAME_RATIO


_LABEL = re.compile(r"^[^,;:]*?\b(?:is|are|was|were)\s+(?:a|an|the)\s+\w")


def is_label(text):
    """A label sentence: a subject with no comma in it, then the first
    is/are/was/were of the sentence within its first twelve words, then
    a/an/the and a word."""
    flat = T._QUOTED.sub("Q", text)
    m = _LABEL.match(flat)
    if not m:
        return False
    head = T.WORD.findall(m.group(0))[:-2]
    subject = {w.lower() for w in head[:-1]}
    return 1 < len(head) <= 11 and not subject & (_COPULA | T.SUBORDINATORS)


def _groups(unit, match):
    """Index lists of three or more sentences within FRAME_WINDOW that match."""
    out, used = [], set()
    for i in range(len(unit)):
        if i in used:
            continue
        members = [i] + [j for j in range(i + 1, min(len(unit), i + FRAME_WINDOW))
                         if j not in used and match(i, j)]
        if len(members) >= 3:
            out.append(members)
            used.update(members)
    return out


def frame_groups(unit):
    """(members, variant) for each group of parallel sentences in a unit."""
    shapes = [T.shape(s["text"]) for s in unit]
    out = [(m, "skeleton") for m in _groups(unit, lambda i, j: same_frame(shapes[i], shapes[j]))]
    taken = {i for m, _v in out for i in m}
    labels = [is_label(s["text"]) for s in unit]
    for m in _groups(unit, lambda i, j: labels[i] and labels[j]):
        if not set(m) <= taken:
            out.append((m, "label"))
    return out


def parallel(unit, text, make):
    found = {"HIGH": []}
    for members, variant in frame_groups(unit):
        what = ("the same sentence frame with the content words changed" if variant == "skeleton"
                else "the frame 'X is a Y'")
        label = (f"{len(members)} sentences in one paragraph use {what}; "
                 "recast one or merge them")
        found["HIGH"].append(T.record(make, text, unit[members[0]], unit[members[-1]],
                                      "structure-parallel", label, variant))
    return found


def triad(unit, text, make):
    found = {"HIGH": [], "LOW": []}
    spans = {(i, j) for i, j, key in opener_runs(unit)
             if j - i == 3 and key[0] not in PRONOUN_OPENERS}
    spans |= {(m[0], m[-1] + 1) for m, _v in frame_groups(unit)
              if len(m) == 3 and m[-1] - m[0] == 2}
    for i, j in sorted(spans):
        label = ("three parallel sentences in a row (rule of three); "
                 "say it in one sentence or drop to two")
        found["HIGH"].append(T.record(make, text, unit[i], unit[j - 1],
                                      "structure-triad", label, "sentences"))
    for sent in unit:
        m = _TRIAD.search(sent["text"])
        if m:
            label = (f"three-item list '{m.group(0)[:60]}' (rule of three); "
                     "keep it if the items are the full set, else cut or add")
            rec = T.record(make, text, sent, sent, "structure-triad", label, "items")
            found["LOW"].append(rec)
    return found


def _statement(sent):
    return sent["text"].rstrip("\"')]”’*_").endswith(".")


def _links(sent):
    words = T.opener(sent["text"], 1)
    return bool(words) and words[0] in T.LINK_OPENERS


def _flat(sent):
    """A statement with no linking word anywhere in it."""
    low = {w.lower() for w in sent["words"]}
    return _statement(sent) and not _links(sent) and not low & (T.SUBORDINATORS | T.COORDINATORS)


def parataxis(unit, text, make):
    found = {"HIGH": [], "MEDIUM": []}
    covered, i = set(), 0
    while i < len(unit):
        j = i
        while (j < len(unit) and len(unit[j]["words"]) <= SHORT_WORDS and _statement(unit[j])
               and not _links(unit[j])):
            j += 1
        if j - i >= RUN_MIN:
            label = (f"{j - i} short statements in a row with no linking word; "
                     "join the ones that depend on each other")
            found["HIGH"].append(T.record(make, text, unit[i], unit[j - 1],
                                          "structure-parataxis", label, "run"))
            covered.update(range(i, j))
        i = max(j, i + 1)
    for k, sent in enumerate(unit):
        if k in covered or len(sent["words"]) > STUB_WORDS or not _flat(sent):
            continue
        para = [s for s in unit if s["pid"] == sent["pid"]]
        if sent["para"] < STUB_PARAGRAPH or any(_links(s) for s in para):
            continue
        label = (f"a {len(sent['words'])}-word statement in a paragraph where no sentence "
                 "links to the one before; attach it to its neighbour")
        found["MEDIUM"].append(T.record(make, text, sent, sent,
                                        "structure-parataxis", label, "stub"))
    return found


def longest_opener_run(units):
    """The longest run of consecutive sentences that share an opener."""
    return max([j - i for unit in units for i, j, _k in opener_runs(unit)] or [1])


def fingerprint():
    return ["RUNS|%s|%s|%s|%s|%s|%s|%s" % (FRAME_RATIO, FRAME_SHORT, FRAME_WINDOW, SHORT_WORDS,
                                           RUN_MIN, STUB_WORDS, STUB_PARAGRAPH),
            _TRIAD.pattern, _LABEL.pattern, repr(sorted(ARTICLES)), repr(sorted(_COPULA)),
            repr(sorted(PRONOUN_OPENERS)),
            repr(sorted(T.LINK_OPENERS)), repr(sorted(T.SUBORDINATORS)),
            repr(sorted(T.COORDINATORS))]
