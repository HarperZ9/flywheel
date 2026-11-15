#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.invariants -- the surface facts a rewrite must keep.

Extracts the surface features of a text whose change usually changes what the
text says: code and math spans, URLs and emails, citations, quoted strings,
project freeze terms, numbers (with units, percentages, dates, times, and
versions), modal strength, scope qualifiers, negations, and named entities.

Each item is a dict with a `kind`, a normalized `key` that two texts are compared
on, the surface `text`, and its `start`/`end` offsets. Container kinds (code,
math, URL, citation, quote, freeze, number) claim their span first and mask it,
so a number inside a URL or a name inside a quote is counted once, as part of its
container. articulate.lexical then reads the word-level kinds (modal, scope,
negation, entity) from the text with every container blanked.

These are surface proxies. A rewrite can keep every one of them and still change
what the text means, and a rewrite can change one of them and keep the meaning.
The meaning module states that limit beside every report. Standard library only.
"""
from __future__ import annotations

import re
import unicodedata

from . import finders, lexical, quantities

KINDS = ("code", "math", "url", "citation", "quote", "freeze", "number",
         "modal", "scope", "negation", "entity")

# No length cap: a negated class that runs to its delimiter stays linear, and a
# cap would leave a long span unprotected.
INLINE_CODE = re.compile(r"``[^\n]+?``|`[^`\n]+`")
# The environments whose body is math, plus the theorem-like ones the 0.4.1 math
# mask protected, because a changed quantifier order changes a theorem. Any
# other environment (document, abstract, itemize) holds prose the model edits.
MATH_ENVS = ("equation", "align", "alignat", "flalign", "gather", "multline",
             "eqnarray", "split", "math", "displaymath", "theorem", "lemma", "proof",
             "definition", "proposition", "corollary", "claim")
# Display math has no length cap either. The finders pair each opener with its
# first closer in linear time, where a lazy regex rescans to the end of the text
# from every unclosed opener.
MATH = finders.display_math_finders(MATH_ENVS)
# Inline $...$ counts as math only when its body carries TeX syntax, so a price
# pair such as "$5 and $10" is not read as one formula.
INLINE_MATH = re.compile(r"\$(?=[^\s$])(?:\\.|[^$\\\n]){1,300}(?<=\S)\$")
TEX_SIGN = re.compile(r"[\\^_{}=<>]")
# The rule packs blank URLs out of a prose line with this pattern. The protected
# spans and the meaning guard find URLs with finders.url_spans, which keeps a
# balanced bracket inside a URL.
URL = re.compile(r"\bhttps?://[^\s<>\"'\])]{1,2000}|\bwww\.[^\s<>\"'\])]{1,2000}"
                  r"|\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}\b")
_YEAR = r"(?:1[6-9]|20)\d{2}[a-z]?"
CITATION = re.compile(
    r"\[-?@[^\]\n]{1,200}\]"                               # pandoc [@key, p. 3]
    r"|\[\^[\w-]{1,40}\]"                                   # footnote [^1]
    r"|\[\d{1,4}(?:\s{0,2}[,\u2013-]\s{0,2}\d{1,4}){0,20}\]"  # numeric [1], [1-3]
    r"|\((?:(?:see|cf\.|e\.g\.),?\s{1,3})?[A-Z][\w'\-]{1,40}"
    r"(?:\s{1,3}et\s{1,3}al\.|\s{1,3}(?:and|&)\s{1,3}[A-Z][\w'\-]{1,40})?,?\s{1,3}"
    + _YEAR + r"(?:,\s{0,2}pp?\.\s{0,2}[\d\u2013-]{1,12})?(?:;[^()\n]{1,120})?\)"
    r"|\b[A-Z][\w'\-]{1,40}\s{1,3}et\s{1,3}al\.(?:\s{0,2}\(" + _YEAR + r"\))?"
    # Narrative author-year: Smith (2020), Smith and Lee (2020, p. 4).
    r"|\b[A-Z][\w'\-]{1,40}(?:\s{1,3}(?:and|&)\s{1,3}[A-Z][\w'\-]{1,40})?\s{1,3}\("
    + _YEAR + r"(?:,\s{0,2}pp?\.\s{0,2}[\d\u2013-]{1,12})?\)"
    # A statute or regulation cited title first: 5 U.S.C. 552, 21 CFR Part 11,
    # 45 C.F.R. 164.512(b), 85 Fed. Reg. 1234. Its title number is no count, so
    # "under 5 U.S.C. 552" is no bound.
    r"|\b\d{1,3}\s{1,3}(?:U\.\s?S\.\s?C\.|C\.\s?F\.\s?R\.|Stat\.|Fed\.\s{1,3}Reg\."
    r"|(?:USC|CFR)\b)(?:\s{1,3}(?:[Pp]art\s{1,3}|\u00a7{1,2}\s{0,2})?\d{1,6}[a-z]?"
    r"(?:\.\d{1,6}[a-z]?){0,2}(?:\([0-9A-Za-z]{1,4}\)){0,6})?"
    r"|\bdoi:\s{0,2}10\.\d{4,9}/[^\s\"<>]{1,200}|\b10\.\d{4,9}/[^\s\"<>]{1,200}"
    r"|\barXiv:\s{0,2}(?:\d{4}\.\d{4,5}|[a-z\-]{2,20}(?:\.[A-Z]{2})?/\d{7})(?:v\d{1,3})?"
    r"|\\cite[tp]?\*?(?:\[[^\]\n]{0,80}\])?\{[^}\n]{1,200}\}")
_TRAIL = finders.TRAIL

# Block-quote markers at a line start, nested quotes included.
_QUOTE_MARKS = re.compile(r"(?:[ ]{0,3}>[ ]?)*")
# Quoted content after which no lazy line follows: a fence, a heading, a rule.
_NO_LAZY_AFTER = re.compile(r"[ ]{0,3}(?:```|~~~|#{1,6}(?:[ \t]|$)|(?:[-*_][ \t]*){3,}$)")
# A line that opens a new block, so it cannot continue a quoted paragraph. A
# line that opens or closes display math also ends the quote, so a '>' line
# inside $$...$$ cannot carry the quote over the closing delimiter.
_INTERRUPTS = re.compile(r"[ ]{0,3}(?:```|~~~|#{1,6}(?:[ \t]|$)|[-+*][ \t]+\S"
                         r"|\d{1,9}[.)][ \t]+\S|\||<[A-Za-z/!?]|(?:[-*_][ \t]*){3,}$"
                         r"|\$\$|\\\[|\\\]|\\begin\{|\\end\{)")


def fenced_blocks(text):
    """(start, end) of each fenced code block, fences included. An unclosed fence
    runs to the end of the text, as a Markdown renderer reads it."""
    out, pos, open_at, fence, fence_length = [], 0, None, "", 0
    for line in text.splitlines(keepends=True):
        body = line.strip()
        if open_at is None and body.startswith(("```", "~~~")):
            open_at, fence = pos, body[0]
            fence_length = len(body) - len(body.lstrip(fence))
        elif (open_at is not None and len(body) >= fence_length
              and set(body) == {fence}):
            out.append((open_at, pos + len(line.rstrip("\r\n"))))
            open_at = None
        pos += len(line)
    if open_at is not None:
        out.append((open_at, len(text.rstrip("\r\n"))))
    return out


def freeze_keys(freeze):
    """The freeze terms as compared: surrounding whitespace dropped, in NFC."""
    return {unicodedata.normalize("NFC", t.strip()) for t in freeze if t and t.strip()}


def freeze_pattern(freeze):
    """A regex for the freeze terms as whole words, longest first, or None. Each
    term matches in its composed (NFC) and decomposed (NFD) form, so "Zo\u00eb"
    matches whichever form the document uses. A combining mark after a match
    means the word goes on, so "Zoe" does not match inside a decomposed
    "Zoe\u0308"."""
    forms = {unicodedata.normalize(f, t) for t in freeze_keys(freeze) for f in ("NFC", "NFD")}
    if not forms:
        return None
    terms = sorted(forms, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in terms)
                      + r")(?![\w\u0300-\u036f])")


def _freeze_pass(rx):
    def run(masked):
        return [(m.start(), m.end(), unicodedata.normalize("NFC", m.group(0)))
                for m in rx.finditer(masked)]
    return run


def blockquotes(text):
    """(start, end) of each Markdown block quote: a run of lines that open with
    '>', plus the lazy continuation lines CommonMark keeps inside it. A lazy
    line is a non-blank line right after quoted paragraph text that opens no
    block of its own (a fence, heading, list item, table row, HTML block, or
    rule). A blank line ends the quote."""
    out, pos, open_at, last_end, lazy = [], 0, None, 0, False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if line.lstrip(" ")[:1] == ">" and len(line) - len(line.lstrip(" ")) <= 3:
            open_at = pos if open_at is None else open_at
            last_end = pos + len(body)
            content = body[_QUOTE_MARKS.match(body).end():]
            lazy = bool(content.strip()) and not _NO_LAZY_AFTER.match(content)
        elif open_at is not None and lazy and body.strip() and not _INTERRUPTS.match(body):
            last_end = pos + len(body)
        elif open_at is not None:
            out.append((open_at, last_end))
            open_at, lazy = None, False
        pos += len(line)
    if open_at is not None:
        out.append((open_at, last_end))
    return out


def _rx_pass(rx, trim=True, keep=None):
    def run(masked):
        out = []
        for m in rx.finditer(masked):
            end = m.end()
            while trim and end > m.start() + 1 and masked[end - 1] in _TRAIL:
                end -= 1
            if keep is None or keep(m.group(0)):
                out.append((m.start(), end, None))
        return out
    return run


def container_passes(freeze=(), *, numbers=True, quotes=True, block_quotes=False,
                     tex=False):
    """The container passes in priority order: (kind, finder). A finder maps the
    current masked text to a list of (start, end, key-or-None). `tex` reads a
    .tex file: every inline $...$ is math, backticks open LaTeX quotes (``like
    this''), so they mark no code, and a '>' line is no block quote. Elsewhere
    inline math needs TeX syntax in its body."""
    passes = [("code", lambda t: [(s, e, None) for s, e in fenced_blocks(t)])]
    if block_quotes and not tex:
        passes.append(("blockquote", lambda t: [(s, e, None) for s, e in blockquotes(t)]))
    if not tex:
        passes.append(("code", _rx_pass(INLINE_CODE, trim=False)))
    passes += [("math", find) for find in MATH]
    passes += [("math", _rx_pass(INLINE_MATH, trim=False,
                                 keep=None if tex else TEX_SIGN.search)),
               ("url", finders.url_spans), ("citation", _rx_pass(CITATION))]
    if quotes:
        passes.append(("quote", finders.quote_spans))
    frx = freeze_pattern(freeze)
    if frx is not None:
        passes.append(("freeze", _freeze_pass(frx)))
    if numbers:
        passes.append(("number", quantities.find))
    return passes


def claim(text, passes):
    """Run the passes in order and return (claims, masked): claims is a list of
    (kind, start, end, key-or-None), and masked is the text with every claimed
    span blanked (newlines kept), so a later pass cannot match inside an earlier
    claim."""
    claims, chars, masked = [], list(text), text
    for kind, finder in passes:
        found = finder(masked)
        for start, end, key in found:
            claims.append((kind, start, end, key))
            for i in range(start, end):
                if chars[i] != "\n":
                    chars[i] = " "
        if found:
            masked = "".join(chars)
    return claims, masked


_DASHES = str.maketrans({"\u2013": "-", "\u2014": "-"})
_CURLY = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
_YEAR_COMMA = re.compile(r"(?<=[A-Za-z.]),? (?=" + _YEAR + r"\b)")


def _citation_key(text):
    """A citation as compared: dashes as '-', '&' as 'and', no comma before the
    year, and no space around ',', ';', or '-'. "(Smith, 2020)" and "(Smith
    2020)" compare equal, and [1-3] matches [1\u20133]."""
    # Collapse whitespace first, so no later pattern scans a long run of it.
    t = re.sub(r"\s+", " ", text.translate(_DASHES)).replace(" & ", " and ")
    return re.sub(r" ?([,;-]) ?", r"\1", _YEAR_COMMA.sub(" ", t))


# The key of each container kind. A formatting-only edit keeps the key, and the
# report still shows each side as written.
_KEYS = {"citation": _citation_key, "quote": lambda t: t.translate(_CURLY)}


def _containers(text, freeze, tex=False, quotes=True):
    claims, masked = claim(text, container_passes(freeze, tex=tex, quotes=quotes))
    items = [lexical.item(kind, _KEYS.get(kind, str)(text[s:e]) if key is None else key,
                          text[s:e], s, e)
             for kind, s, e, key in claims]
    return items, masked


def extract(text, *, freeze=(), tex=False, quotes=True):
    """Every surface invariant in `text`, in document order within each kind.
    `tex` reads the text as a .tex file (see container_passes). With `quotes`
    off, quoted material is prose: no quote item, and its words yield their own
    numbers, negations, and names."""
    containers, masked = _containers(text, tuple(freeze), tex, quotes)
    numbers = frozenset(i["start"] for i in containers if i["kind"] == "number")
    items = containers + lexical.tokens(masked, freeze_keys(freeze), numbers)
    items.sort(key=lambda i: (KINDS.index(i["kind"]), i["start"]))
    return items
