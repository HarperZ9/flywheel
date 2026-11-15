"""Paragraphs, sentences and token shapes for the structure rule pack.

The pack reads prose one paragraph at a time. `paragraphs` groups the prose
lines a pack receives into paragraphs and splits each into sentence records
that carry absolute offsets, so a finding can span a run of sentences. A
heading, a list item, a table row and a block quote are structure, and they
are left out. Adjacent one-sentence paragraphs are read as one unit, since a
post written one sentence to a line has the same rhythm as a paragraph.

`list_items` reads each list item as its own short paragraph, marker and
checkbox blanked, for the rules that judge one sentence by its place (pin,
pointer, landing). The run rules never read a list: three items that open on
one word are a list doing its job.

A quoted span is a mention, so a full stop inside one ends no sentence: the
quoted line stays inside the sentence that quotes it.

`shape` turns a sentence into a token-shape signature with no parser: a
function word stays as itself, a quoted span becomes Q, a number becomes #,
and every other word becomes its ending class (s, ed, ing, ly) or a blank.
Two sentences with the same signature differ only in their content words.
Standard library only.
"""
from __future__ import annotations

import re

from . import pack_util
from .wordlists import FUNCTION_WORDS

WORD = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
_END = re.compile(r"[.!?]+[\"')\]”’*_]*(?=\s|$)|:(?=\s*$)")
_ABBREV = re.compile(r"(?:\b(?:e\.g|i\.e|etc|vs|cf|Mr|Mrs|Ms|Dr|St|Inc|Jr|Sr|No|Fig)|\b[A-Z])\.$")
_QUOTED = re.compile(r"\"[^\"\n]{3,}?\"|“[^”\n]{3,}?”")
_NUMBER = re.compile(r"^\d[\d,.]*$")
_LETTER = re.compile(r"[A-Za-z]")
_BOLD_LABEL = re.compile(r"^(?:\*\*|__)(?:\d+[.)]\s*)?[^*_\n]{1,80}(?:\*\*|__)[.:]?$")
_LEAD = re.compile(r"^[\s\"'“‘(\[*_]+")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?")

# Words that tie a sentence to the one before it when they open the sentence.
LINK_OPENERS = frozenset(
    "and but so or yet nor because since although though while whereas when if once after "
    "before until unless as then also however still therefore thus instead meanwhile "
    "otherwise besides hence afterwards later next finally first second third".split())
# Words that tie one clause to another inside a sentence.
SUBORDINATORS = frozenset(
    "because since although though while whereas when whenever if unless until once after "
    "before which who whom whose where that so whether".split())
COORDINATORS = frozenset("and but or nor yet".split())


def tokens(text):
    """Words of a sentence, with each quoted span collapsed to the token Q."""
    return WORD.findall(_QUOTED.sub(" Q ", text))


def _class(word):
    low = word.lower()
    if word == "Q":
        return "Q"
    if _NUMBER.match(word):
        return "#"
    if low in FUNCTION_WORDS:
        return low
    for end, least in (("ing", 5), ("ed", 4), ("ly", 4)):
        if low.endswith(end) and len(low) >= least:
            return end
    if low.endswith("s") and not low.endswith("ss") and len(low) >= 4:
        return "s"
    return "_"


def shape(text):
    """The token-shape signature of a sentence, as a tuple."""
    return tuple(_class(w) for w in tokens(text))


def opener(text, count=1):
    """The first `count` words of a sentence, lowercased, as a tuple."""
    words = WORD.findall(_LEAD.sub("", text))
    return tuple(w.lower() for w in words[:count])


def _runs_on(joined, m):
    """True when a full stop sits inside a closing quote or bracket and the
    sentence runs on in lower case, as in: the line ("That is all.") stays."""
    rest = joined[m.end():].lstrip()
    return m.group()[-1] in "\"')]”’" and rest[:1].islower()


def _split(joined, base):
    """Sentence records for one paragraph's text; `base` is its absolute offset."""
    out, pos = [], 0
    quoted = [q.span() for q in _QUOTED.finditer(joined)]
    ends = [m for m in _END.finditer(joined)
            if not _ABBREV.search(joined[max(0, m.start() - 8):m.start() + 1])
            and not _runs_on(joined, m)
            and not any(a < m.start() and m.end() < b for a, b in quoted)]
    for m in ends + [None]:
        end = m.end() if m else len(joined)
        chunk = joined[pos:end]
        body = chunk.strip()
        if m and not _LETTER.search(body):
            continue                      # "1." or "**2." opens the sentence after it
        if _BOLD_LABEL.match(body):
            pos = end
            continue                      # a bold lead-in is a label, like a heading
        if body and WORD.search(body):
            start = pos + len(chunk) - len(chunk.lstrip())
            out.append({"text": body, "start": base + start, "end": base + start + len(body),
                        "words": WORD.findall(body)})
        pos = end
    return out


def _groups(prose):
    """Runs of contiguous prose lines that form one paragraph. A structure line
    (heading, list item, quote, table row) or a gap in the offsets closes a run.
    The wrapped lines under a list marker belong to the item: `list_items` reads
    them, and here they are skipped, so a line fragment is never a paragraph."""
    group, expect, item_next = [], None, None
    for rec in prose:
        _line, off, raw, masked = rec
        blank = not masked.strip()
        block = bool(pack_util._BLOCK.match(masked))
        marker = bool(_ITEM.match(masked))
        wrapped = not blank and not block and not marker and off == item_next
        item_next = off + len(raw) if marker or wrapped else None
        skip = blank or block or marker or wrapped
        if skip or (expect is not None and off != expect):
            if group:
                yield group
            group = []
            expect = None
            if skip:
                continue
        group.append(rec)
        expect = off + len(raw)
    if group:
        yield group


def paragraphs(prose):
    """A list of paragraphs, each a list of sentence records. A record adds
    `line`, `line_off` and `raw` for the line the sentence starts on, `pid` for
    its paragraph, `first`
    and `last` for its place in its own paragraph, and `para` for the size of
    that paragraph. Adjacent one-sentence paragraphs are merged into one unit."""
    units = []
    for pid, group in enumerate(_groups(prose)):
        base = group[0][1]
        sents = _split("".join(rec[3] for rec in group), base)
        for i, s in enumerate(sents):
            owner = [rec for rec in group if rec[1] <= s["start"]][-1]
            s.update(line=owner[0], line_off=owner[1], raw=owner[2], pid=pid,
                     first=i == 0, last=i == len(sents) - 1, para=len(sents))
        if not sents:
            continue
        if len(sents) == 1 and units and units[-1][-1]["para"] == 1:
            units[-1].append(sents[0])
        else:
            units.append(sents)
    return units


def list_items(prose):
    """A list of list items, each a list of sentence records shaped like the
    ones `paragraphs` returns, with `item` set. An item is its marker line and
    the wrapped lines under it; a blank line, another marker or a block line
    ends it. The marker and a task checkbox are blanked, so offsets hold."""
    items, group, expect = [], [], None
    for rec in prose:
        _line, off, raw, masked = rec
        mark = _ITEM.match(masked)
        wrapped = (group and off == expect and masked.strip()
                   and not pack_util._BLOCK.match(masked))
        if mark or not wrapped:
            if group:
                items.append(group)
            group = []
        if mark:
            rec = (rec[0], off, raw, " " * mark.end() + masked[mark.end():])
        if mark or wrapped:
            group.append(rec)
            expect = off + len(raw)
    if group:
        items.append(group)
    units = []
    for n, group in enumerate(items):
        sents = _split("".join(rec[3] for rec in group), group[0][1])
        for i, s in enumerate(sents):
            owner = [rec for rec in group if rec[1] <= s["start"]][-1]
            s.update(line=owner[0], line_off=owner[1], raw=owner[2], pid=("item", n),
                     first=i == 0, last=i == len(sents) - 1, para=len(sents), item=True)
        if sents:
            units.append(sents)
    return units


def record(make, text, first, last, category, label, variant):
    """A finding that spans from sentence `first` to sentence `last`."""
    start = first["start"] - first["line_off"]
    end = last["end"] - first["line_off"]
    rec = make(first["line"], first["line_off"], category, label, start, end, first["raw"],
               first["raw"].strip()[:100])
    rec["match"] = text[first["start"]:last["end"]]
    rec["rule_id"] = "%s/%s" % (category, variant)
    return rec
