"""Two series checks for one author's turns or documents: sentence templates
and opening or closing rituals.

A single-passage check cannot see a sentence that is ordinary once and a
stamp the fourth time. `sentence_template` reduces every sentence to a
skeleton: a name, a number and every content word become a slot, the
possessives (my, your, yours, his, theirs and the rest) become one token, and
the function words stay. A phrase of three to six tokens from the last eight
tokens of a skeleton, with three or more kept words (two when the phrase ends
the sentence on a finite verb and a marked word) and one of them outside the commonest function words, is a
template when enough documents end a sentence on it. It is reported with each sentence it came from. "A reply in his name is his to write or approve" and "The question is
yours to answer too" share the template "is POSS to _".

`ritual` compares the first sentence of each document, and the last: the same
two opening words, or the same skeleton, in enough documents is a ritual.

Both report only. The triggers come from corpus_features.THRESHOLDS.
Standard library only.
"""
import re

from . import corpus_features as cf
from . import rules_ext
from . import structure_text as S
from .corpus_checks import _kept, _loc, _protect
from .wordlists import FUNCTION_WORDS

T = cf.THRESHOLDS
POSSESSIVES = frozenset("my your his her their our its mine yours hers theirs ours".split())
# Function words too common to mark a template on their own.
COMMON = frozenset("the a an of to in on and or is are was were it that this for with as at by "
                   "be not from but have has had i we you he she they me him them".split())


_ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+")     # a list item is read as prose here
FINITE = frozenset("is are was were has have had do does did will would can could should "
                   "must may might".split())


def _token(word):
    low = word.lower()
    if low.endswith(("'s", "’s")):
        return "_"
    if low in POSSESSIVES:
        return "POSS"
    if S._NUMBER.match(word):
        return "#"
    if low in FUNCTION_WORDS:
        return low
    return "_"


def skeleton(text):
    """The template skeleton of one sentence: a tuple with slot runs joined."""
    out = []
    for word in S.tokens(text):
        tok = "_" if word == "Q" else _token(word)
        if tok != "_" or not out or out[-1] != "_":
            out.append(tok)
    return tuple(out)


def _sentences(doc):
    """(line, text, skeleton) for each prose sentence of a document."""
    prose = [(n, off, raw, _ITEM.sub(lambda m: " " * len(m.group(0)), masked))
             for n, off, raw, masked in rules_ext.prose_lines(doc["text"].splitlines(keepends=True))]
    return [(s["line"], s["text"], skeleton(s["text"]))
            for unit in S.paragraphs(prose) for s in unit]


def _marked(gram, final):
    """True for a phrase that can carry a template: enough kept words, one of
    them outside COMMON. A phrase that ends its sentence needs one fewer when
    one of its words is a finite verb, as in "_ is POSS"."""
    kept = [t for t in gram if t not in ("_", "#")]
    if not any(t not in COMMON for t in kept):
        return False
    if len(kept) >= T["template_literals"]:
        return True
    return final and len(kept) == T["template_literals"] - 1 and bool(FINITE & set(kept))


def _need(ctx):
    return T["template_docs_small"] if len(ctx["docs"]) <= 3 else T["template_docs"]


def sentence_template(ctx):
    if ctx["single"]:
        return []
    seen = {}                     # gram -> {doc: (line, text)}
    for d in ctx["docs"]:
        for line, text, skel in _sentences(d):
            skel = skel[-T["template_tail"]:]     # where a sentence lands, not its middle
            for n in range(3, 7):
                for i in range(len(skel) - n + 1):
                    gram = skel[i:i + n]
                    if _marked(gram, i + n == len(skel)):
                        seen.setdefault(gram, {}).setdefault(d["name"], (line, text))
    need = _need(ctx)
    grams = sorted((g for g, per in seen.items() if len(per) >= need),
                   key=lambda g: (-len(seen[g]), -len(g), g))
    out, covered = [], []
    for gram in grams:
        docs = set(seen[gram])
        if any(docs <= c for c in covered):
            continue              # a shorter or rarer phrase of a template already reported
        covered.append(docs)
        phrase = " ".join(gram)
        if _kept(ctx, phrase):
            _protect(ctx, "corpus/sentence-template", phrase, docs)
            continue
        locs = [_loc(name, line, line, text) for name, (line, text) in sorted(seen[gram].items())]
        out.append(ctx["finding"]("corpus/sentence-template", list(docs), locs,
                                  {"template": phrase, "docs": len(docs),
                                   "share": round(len(docs) / len(ctx["docs"]), 3)}))
    return out[:T["template_report"]]


def _edges(d):
    rows = _sentences(d)
    return (rows[0], rows[-1]) if rows else (None, None)


def ritual(ctx):
    if ctx["single"]:
        return []
    need = max(_need(ctx), int(T["ritual_share"] * len(ctx["docs"]) + 0.999))
    out = []
    for place, pick in (("opening", 0), ("closing", 1)):
        by_words, by_skel = {}, {}
        for d in ctx["docs"]:
            row = _edges(d)[pick]
            if not row:
                continue
            line, text, skel = row
            words = S.opener(text, 2)
            if len(words) == 2 and not set(words) <= COMMON:
                by_words.setdefault(" ".join(words), {})[d["name"]] = (line, text)
            if 3 <= len(skel) <= 12:
                by_skel.setdefault(" ".join(skel), {})[d["name"]] = (line, text)
        for kind, table in (("words", by_words), ("skeleton", by_skel)):
            for key, per in sorted(table.items()):
                if len(per) < need or _kept(ctx, key):
                    continue
                locs = [_loc(name, line, line, text) for name, (line, text) in sorted(per.items())]
                out.append(ctx["finding"]("corpus/ritual", list(per), locs,
                                          {"place": place, "kind": kind, "shape": key,
                                           "docs": len(per),
                                           "share": round(len(per) / len(ctx["docs"]), 3)}))
    return out


CHECKS = [sentence_template, ritual]
