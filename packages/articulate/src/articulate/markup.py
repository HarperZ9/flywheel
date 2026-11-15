#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.markup -- markup masks, structure tests, sentence splitting and the
span-record builder. Standard library only.
"""
import re

from . import masking

# A file may exempt its terms of art with a line like:
#   writing-allow: substrate, load-bearing, first-class
# in the first 15 lines (works inside an HTML comment, a LaTeX %-comment, or
# YAML frontmatter). Matched text containing an allowed term is not reported.
ALLOW_HELP = ("writing-allow: a line such as `writing-allow: substrate, load-bearing` in "
              "the first 15 lines (an HTML comment, a %-comment or YAML front matter "
              "works) keeps those terms for the whole file: a finding whose matched "
              "text contains an allowed term as a substring, in any case, is dropped. "
              "It reaches every rule, the HIGH tier included, except the contrast "
              "and cadence devices, the em dash and emoji. A substring match is broad: "
              "allowing 'revolutionary' also clears 'a revolutionary product'.")
ALLOW_TAG = re.compile(r"writing-allow:\s*([^\n>%]+)", re.I)


def read_allowlist(lines):
    allow = set()
    for raw in lines[:15]:
        m = ALLOW_TAG.search(raw)
        if m:
            for term in m.group(1).split(","):
                term = term.strip().lower().strip("-").strip()
                if term:
                    allow.add(term)
    return allow


def allowed(matched_text, allow):
    if not allow:
        return False
    low_text = matched_text.lower()
    return any(term in low_text for term in allow)


# The terms-of-art allowlist protects register and jargon VOCABULARY. It must not
# un-flag a banned rhetorical DEVICE just because a kept word happens to sit inside
# the device's wide match span (e.g. "does not utilize X, but Y" is antithesis
# whatever the vocabulary). These device categories always fire; the allowlist is
# not consulted for them.
ALLOW_EXEMPT_CATEGORIES = frozenset({
    "antithesis", "corrective-negation", "substitution", "negative-parallel",
    # Cadence tells are structural, not vocabulary: a summary-beat like "That is
    # the load-bearing part" is a tell whatever the vocabulary, so a terms-of-art
    # allowlist (which keeps "load-bearing", "substrate") must not un-flag it. Same
    # rationale as the device categories above; the contrast-pair pass already
    # bypasses the allowlist for the same reason.
    "cadence",
})

# The reference patterns for the markup masks. strip_markup and mask_quotes
# apply them through articulate.masking, which returns what re.sub with these
# patterns returns, in linear time. Calling .sub with them on a long line that
# never completes a match is quadratic, so the detector does not do that.
TAG = re.compile(masking.TAG_PATTERN)
TEX = re.compile(r"\\[a-zA-Z]+\*?\{?|[{}]")
INLINE_CODE = re.compile(r"`[^`]*`")
URL = re.compile(masking.URL_PATTERN)
FENCE = re.compile(r"^\s*(```|~~~)")

# Text inside a matched pair of quotation marks is spoken dialogue or a cited
# quote: the speaker's words, not the author's prose to fix. A genre that opts
# into dialogue exemption masks these spans (equal-length, so a match offset in
# the masked line stays valid in the raw line) before the device passes run.
# Straight single quotes are left alone because an apostrophe would open a false
# span; double quotes and curly pairs are the reliable dialogue markers.
QUOTED = re.compile(masking.QUOTED_PATTERN)

# A screenplay line, classified by role before any prose rule runs. Sluglines,
# character cues, parentheticals, and transitions are structure, not prose;
# dialogue carries the character's voice; only action faces economy scrutiny.
FOUNTAIN_SLUG = re.compile(r"^\s*(?:INT|EXT|EST|INT\.?/EXT|I/E)[\.\s]", re.I)
FOUNTAIN_FORCED_SLUG = re.compile(r"^\s*\.[^\.\s]")
FOUNTAIN_TRANSITION = re.compile(r"^\s*(?:(?:[A-Z][A-Z \.']+ )?(?:TO|IN|OUT)[:\.]|>.*)\s*$")
FOUNTAIN_PAREN = re.compile(r"^\s*\(.*\)\s*$")
FOUNTAIN_CUE = re.compile(r"^\s*(?:@?[A-Z][A-Z0-9 .'\-]{0,34})(?:\s*\((?:V\.O\.|O\.S\.|"
                          r"CONT'?D|CONT|O\.C\.)\))?\s*$")


# C2PA 2.4 Annex A.9 embeds a manifest reference in structured text between
# these delimiters (in front matter or one comment line). Annex A.8 embeds in
# unstructured text as a run of Unicode variation selectors. Either is a
# credential, never prose, so both are blanked before any rule runs.
C2PA_BEGIN = "-----BEGIN C2PA MANIFEST-----"
C2PA_END = "-----END C2PA MANIFEST-----"
C2PA_MIN_SELECTORS = 4
_VS_RUN = re.compile("[\ufe00-\ufe0f\U000e0100-\U000e01ef]{%d,}" % C2PA_MIN_SELECTORS)


def mask_c2pa(text):
    """The text with every C2PA A.9 block and every A.8 selector run replaced by
    spaces. Line breaks are kept, so every offset stays valid. Linear time."""
    out, pos = [], 0
    while True:
        b = text.find(C2PA_BEGIN, pos)
        if b < 0:
            break
        e = text.find(C2PA_END, b)
        e = len(text) if e < 0 else e + len(C2PA_END)
        out.append(text[pos:b])
        out.append("".join(c if c == "\n" else " " for c in text[b:e]))
        pos = e
    out.append(text[pos:])
    return _VS_RUN.sub(lambda m: " " * len(m.group(0)), "".join(out))


def _blank(m):
    return " " * (m.end() - m.start())


def strip_markup(line: str) -> str:
    """Mask code, URLs, HTML tags, and LaTeX with equal-length spaces. Length is
    preserved so a match offset in the masked line is a valid offset in the raw
    line, which is what span-level records need."""
    line = INLINE_CODE.sub(_blank, line)
    line = masking.mask_urls(line)    # URL.sub, in linear time
    line = masking.mask_tags(line)    # TAG.sub, in linear time
    line = TEX.sub(_blank, line)
    return line


def mask_quotes(line: str) -> str:
    """Mask quoted speech with equal-length spaces so a device inside a quote is
    not scored against the author. Offsets are preserved for span records."""
    return masking.mask_quoted(line)   # QUOTED.sub, in linear time


def classify_fountain(lines):
    """Classify each screenplay line by Fountain role: slugline, action,
    character (a cue), parenthetical, dialogue, or transition. Cues and dialogue
    are recognized by position (an all-caps cue, then the lines under it until a
    blank), so only action lines carry prose-economy scrutiny and dialogue keeps
    the character's voice. A heuristic, not a full Fountain parser."""
    roles = ["action"] * len(lines)
    prev_blank = True
    in_dialogue = False
    for i, raw in enumerate(lines):
        text = raw.strip()
        if not text:
            roles[i] = "blank"
            prev_blank = True
            in_dialogue = False
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if FOUNTAIN_SLUG.match(text) or FOUNTAIN_FORCED_SLUG.match(text):
            roles[i] = "slug"
            in_dialogue = False
        elif FOUNTAIN_TRANSITION.match(text) and text.upper() == text:
            roles[i] = "transition"
            in_dialogue = False
        elif in_dialogue and FOUNTAIN_PAREN.match(text):
            roles[i] = "parenthetical"
        elif in_dialogue:
            roles[i] = "dialogue"
        elif prev_blank and nxt and FOUNTAIN_CUE.match(text) and any(c.isalpha() for c in text):
            roles[i] = "character"
            in_dialogue = True
        else:
            roles[i] = "action"
            in_dialogue = False
        prev_blank = False
    return roles


def _rid(category: str, label: str) -> str:
    """A stable, human-readable rule id for a receipt: category/label-slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:48]
    return f"{category}/{slug}" if slug else category


def _mk(line_no, offset, category, label, start, end, raw, snippet):
    """Build a span-level finding record for a match inside one physical line."""
    return {
        "line": line_no, "end_line": line_no, "col": start + 1,
        "start": offset + start, "end": offset + end,
        "category": category, "label": label,
        "match": raw[start:end], "snippet": snippet,
        "rule_id": _rid(category, label),
    }


def is_md_hr(line: str) -> bool:
    return re.fullmatch(r"\s*-{3,}\s*", line) is not None


_TABLE_CELL = re.compile(r":?-+:?")


def is_md_table_sep(line: str) -> bool:
    """True for a Markdown table delimiter row such as `|---|:---:|` or `---|---`.
    The row is table structure, so its hyphen runs are never an em-dash. A row needs
    at least one pipe, which keeps a bare `---` a thematic break. Every cell must be
    hyphens with optional alignment colons, so a content row that happens to carry
    `---` or an em-dash stays under the em-dash rule. Split and fullmatch per cell,
    so the check is linear in the line length."""
    s = line.strip()
    if "|" not in s or "-" not in s:
        return False
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return all(_TABLE_CELL.fullmatch(cell.strip()) for cell in s.split("|"))


def split_sentences(text: str):
    # Rough sentence split for cadence stats. Good enough to spot uniformity.
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def _line_offsets(lines):
    offsets, acc = [], 0
    for raw in lines:
        offsets.append(acc)
        acc += len(raw)
    return offsets
