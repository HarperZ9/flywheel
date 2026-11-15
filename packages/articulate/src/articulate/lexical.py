#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.lexical -- the word-level invariants: modal strength, scope words,
negations, and named entities.

`tokens(masked, freeze_keys)` reads them from a text whose containers (code,
math, URLs, citations, quotes, freeze terms, numbers) articulate.invariants has
already blanked, so a word inside a container is counted once, as part of it.
Each item has the shape of an invariants item: `kind`, a normalized `key`, the
surface `text`, and its `start` and `end` offsets. Standard library only.
"""
from __future__ import annotations

import bisect
import re

_MODAL = re.compile(
    r"(?i)\b(?:(must|shall|should|may|might|can|could)(?=n['\u2019]t\b|not\b|\b)"
    r"|(sha)(?=n['\u2019]t\b)|(required|recommended|optional)\b"
    r"|(ought\s{1,3}to|ha(?:ve|s|d)\s{1,3}to|needs?\s{1,3}to)\b"
    # Ability reads as the optional class, as "can" does: "is able to", "is not
    # able to", "is unable to", "has the ability to".
    r"|((?:is|are|am|be|been|being|was|were)(?:n['\u2019]t|\s{1,3}not)?\s{1,3}(?:un)?able"
    r"\s{1,3}to|ha(?:s|ve|d)\s{1,3}the\s{1,3}ability\s{1,3}to)\b)")
_ABILITY = 5
_MODAL_CLASS = {"must": "required", "shall": "required", "sha": "required",
                "required": "required", "have": "required", "has": "required",
                "had": "required", "need": "required", "needs": "required",
                "should": "recommended", "recommended": "recommended",
                "ought": "recommended", "may": "optional", "might": "optional",
                "can": "optional", "could": "optional", "optional": "optional"}
BCP14 = frozenset({"MUST", "SHALL", "SHOULD", "MAY", "REQUIRED", "RECOMMENDED",
                   "OPTIONAL"})
# The comparatives. "no more than" and "not fewer than" are bounds (at most and
# at least), so their "no" or "not" belongs to the bound and is no negation.
_MORE = r"more|greater|higher|larger|longer"
_LESS = r"less|fewer|lower|smaller|shorter"
_NEG_CMP = r"not?\s{1,3}(?:" + _MORE + "|" + _LESS + r"|later|earlier)\s{1,3}than\b"
# Scope groups as (key, pattern, bounds a number). A group that bounds a number
# counts only when a number or date starts one to three spaces after it, so
# "over 50%" and "up to 10 MB" bound a claim, and "over the network" and "up to
# date" are prose. Synonyms share a key, so "under 50%" matches "below 50%".
_SCOPE_GROUPS = (
    # Idioms that hold a quantifier or bound word and quantify nothing. They
    # match first and yield no item. "after all" is the idiom only when no word
    # follows it, so "after all tests pass" keeps its quantifier, and "at all
    # times" is "always".
    (None, r"at\s{1,3}all(?!\s{1,3}times\b)|after\s{1,3}all(?!\s{1,3}\w)|above\s{1,3}all"
           r"|all\s{1,3}(?:right|in\s{1,3}all)|(?:first|most|last)\s{1,3}of\s{1,3}all", False),
    ("only", r"only|solely|exclusively", False),
    ("unless", r"unless", False),
    ("except", r"except", False),
    ("at-least", r"at\s{1,3}least|not?\s{1,3}(?:" + _LESS + r"|earlier)\s{1,3}than"
                 r"|a\s{1,3}minimum\s{1,3}of", False),
    ("at-most", r"at\s{1,3}most|not?\s{1,3}(?:" + _MORE + r"|later)\s{1,3}than"
                r"|a\s{1,3}maximum\s{1,3}of", False),
    ("at-most", r"up\s{1,3}to", True),
    ("more-than", r"(?:" + _MORE + r")\s{1,3}than|over|above|exceed(?:s|ed|ing)?", True),
    ("less-than", r"(?:" + _LESS + r")\s{1,3}than|under|below", True),
    ("before", r"before|prior\s{1,3}to|earlier\s{1,3}than", True),
    ("after", r"after|later\s{1,3}than|subsequent\s{1,3}to", True),
    ("always", r"always|at\s{1,3}all\s{1,3}times", False),
    ("exactly", r"exactly", False),
    # Quantifiers and frequency words, one key per strength.
    ("universal", r"all|every|each(?!\s{1,3}other\b)", False),
    ("existential", r"some|several|a\s{1,3}few", False),
    ("usually", r"usually|typically|normally", False),
    ("often", r"often|frequently", False),
    ("sometimes", r"sometimes|occasionally", False),
    ("rarely", r"rarely|seldom", False),
)
_SCOPE = re.compile(r"(?i)\b(?:" + "|".join(f"({p})" for _k, p, _b in _SCOPE_GROUPS)
                    + r")\b")
# A hyphen compound that opens with "no" ("no-brainer", "no-op") negates
# nothing, but "no-one" does.
_NEGATION = re.compile(r"(?i)\b(?:never|none|nothing|nobody|nowhere|without|neither"
                       r"|nor|cannot|unable)\b|n['\u2019]t\b"
                       r"|\b(?!" + _NEG_CMP + r")(?:not\b|no\b(?!\.\s?\d"
                       r"|[-\u2010\u2011](?!one\b)))")
_ENTITY = re.compile(r"\b[A-Z][A-Za-z0-9]{0,40}(?:[.+\-][A-Za-z0-9]{1,40}){0,4}"
                     r"(?:['\u2019]s)?\b")
# A name that opens with a lower-case letter: macOS, iPhone, gRPC, eBay. The
# capital inside it marks it as a name wherever it stands.
_CAMEL = re.compile(r"\b[a-z]{1,10}[A-Z][A-Za-z0-9]{0,40}(?:['\u2019]s)?\b")
_HEADING = re.compile(r"[ ]{0,3}#")
# What may stand between a negation and the modal it negates: spaces and at
# most one word, as in "is not strictly required".
_BEFORE_MODAL = re.compile(r"\s{1,3}(?:[A-Za-z]{1,20}\s{1,3})?")
_NOT_ENTITY = BCP14 | {"I", "NOT"}
_LEAD_MARKUP = re.compile(r"(?:^|\s)(?:[-+*]|\d{1,3}[.)])$")


def item(kind, key, text, start, end, **extra):
    """One invariant record."""
    rec = {"kind": kind, "key": key, "text": text, "start": start, "end": end}
    rec.update(extra)
    return rec


def _is_initial(masked, pos, starts):
    """True when a token opens a sentence or a block: the start of a line after a
    blank or a sentence end, or right after '.', '!', '?', or ':'. It reads a
    bounded window before the token, so a long single-line input stays linear."""
    k = bisect.bisect_right(starts, pos) - 1
    line_start = starts[k]
    lo = max(line_start, pos - 160)
    raw = masked[lo:pos]
    prefix = _LEAD_MARKUP.sub("", raw.rstrip(" \t*_#>([\"'\u201c\u2018|~")).rstrip()
    if prefix:
        return prefix[-1] in ".!?:"
    if k == 0 or raw.strip() or lo > line_start:
        return True
    last_line = masked[starts[k - 1]:line_start].strip()
    # A wrapped prose line continues the sentence above it; a blank line, a
    # sentence end, a heading, or a table row above starts a new block.
    return (not last_line or last_line[-1] in ".!?:"
            or last_line.startswith(("#", "|", "```", "~~~")))


def _bounds_number(masked, end, number_starts):
    """True when a number claim starts one to three spaces after `end`. The
    number itself is blanked in `masked`, so the offsets come from its claim."""
    for gap in (1, 2, 3):
        if end + gap in number_starts:
            return masked[end:end + gap].isspace()
    return False


def _negation_side(masked, m, negs):
    """(start, end, prefix, suffix) of a modal widened to a negation beside it.
    A negation right after the modal ("must not", "mustn't", "cannot") negates
    what follows, and adds "+not". A negation up to one word before it ("do not
    have to", "is not strictly required") negates the modal, and adds "not-"."""
    starts, ends = negs
    start, end, prefix, suffix = m.start(), m.end(), "", ""
    i = bisect.bisect_left(starts, start)
    if i < len(starts):
        gap = masked[end:starts[i]]
        if starts[i] < end or gap == "" or (len(gap) <= 2 and gap.isspace()):
            end, suffix = max(end, ends[i]), "+not"
    j = bisect.bisect_right(ends, start) - 1
    if j >= 0 and _BEFORE_MODAL.fullmatch(masked, ends[j], start):
        start, prefix = starts[j], "not-"
        # Widen to the whole word, so the report shows "don't have to".
        while start > max(0, starts[j] - 20) and masked[start - 1].isalpha():
            start -= 1
    return start, end, prefix, suffix


def _modal_items(masked, negs):
    items = []
    for m in _MODAL.finditer(masked):
        word = m.group(0)
        head = re.split(r"\s", word, maxsplit=1)[0].lower()
        start, end, prefix, suffix = _negation_side(masked, m, negs)
        cls = "optional" if m.group(_ABILITY) else _MODAL_CLASS[head]
        if cls == "recommended" and prefix:
            # "not recommended" advises against, as "should not" does, and RFC
            # 2119 makes NOT RECOMMENDED a synonym of SHOULD NOT.
            prefix, suffix = "", "+not"
        key = prefix + cls + suffix + (":BCP14" if word in BCP14 else "")
        items.append(item("modal", key, masked[start:end], start, end))
    return items


def tokens(masked, freeze_keys, number_starts=frozenset()):
    """The word-level items, read from the masked text. `number_starts` holds
    the start offset of each number claim."""
    negations = [item("negation", "negation", m.group(0), m.start(), m.end())
                 for m in _NEGATION.finditer(masked)]
    negs = ([n["start"] for n in negations], [n["end"] for n in negations])
    scopes, scope_words = _scope_items(masked, number_starts)
    return (_modal_items(masked, negs) + negations + scopes
            + _entity_items(masked, freeze_keys, scope_words))


def _scope_items(masked, number_starts):
    """The scope items, and the start of every scope word, counted or not."""
    items, words = [], set()
    for m in _SCOPE.finditer(masked):
        words.add(m.start())
        key, _p, bound = _SCOPE_GROUPS[m.lastindex - 1]
        if key and (not bound or _bounds_number(masked, m.end(), number_starts)):
            items.append(item("scope", key, m.group(0), m.start(), m.end()))
    return items, words


def _entity_items(masked, freeze_keys, skip):
    """Capitalized words, acronyms, and lower-case-initial names. A scope word at
    a sentence start ("All", "Only", "After") is a function word and no name, so
    its start is skipped. `heading` marks a name on a Markdown heading line."""
    items, starts = [], [0] + [m.end() for m in re.finditer("\n", masked)]
    for m in list(_ENTITY.finditer(masked)) + list(_CAMEL.finditer(masked)):
        word = m.group(0)
        key = re.sub(r"['\u2019]s$", "", word)
        if key in _NOT_ENTITY or key in freeze_keys or m.start() in skip:
            continue
        acronym = sum(c.isupper() for c in key) >= 2 or any(c.isdigit() for c in key)
        weak = key[0].isupper() and not acronym and _is_initial(masked, m.start(), starts)
        line = starts[bisect.bisect_right(starts, m.start()) - 1]
        items.append(item("entity", key, word, m.start(), m.end(), weak=weak,
                          heading=bool(_HEADING.match(masked, line))))
    return items
