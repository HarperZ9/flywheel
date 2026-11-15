#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.citations -- the `unsupported-authority` rule and what anchors it.

An appeal to unnamed studies or experts gives the reader no source to check. A
citation marker in any common style gives one, so the rule reads the whole
sentence for a marker, including a marker placed right after its closing
period. A year counts only in citation position (in parentheses, or after an
author name), so a count such as "in 1200 patients" does not silence the rule.
"Our data show", "these data show" and "this data shows" name the writer's own
evidence when the sentence also points at a figure, a table, supplementary
material or a test statistic.

The markers are read on the raw sentence (before markup is blanked), because a
LaTeX `\\cite` or an HTML `<sup>` is markup. Every mask the scanner applies keeps
lengths equal, so the raw and masked sentences share offsets.

Standard library only.
"""
import re

AUTHORITY = re.compile(r"(?i)\b(?:(?P<own>(?:our|these|this)\s+)?data\s+shows?"
                       r"|studies (?:have )?show(?:n)?|research (?:shows|suggests|indicates)"
                       r"|experts agree|scientists say)\b")

_YEAR = r"(?:1[5-9]|20)\d\d[a-z]?"
_NOT_NAME = (r"(?:In|On|By|Since|Until|From|During|After|Before|Of|At|For|And|The|"
             r"Circa|Around|Through|To|January|February|March|April|May|June|July|"
             r"August|September|October|November|December|Spring|Summer|Autumn|"
             r"Fall|Winter)\b")
# A label and a number in parentheses that points inside the document, never an
# author and a page: "(Figure 3)", "(Table 2)", "(Section 4)".
_NOT_AUTHOR = (r"(?:Fig|Figs|Figure|Figures|Table|Tables|Section|Sec|Chapter|Ch|Eq|"
               r"Equation|Appendix|Supplementary|Suppl|Step|Item|Box|Panel|Part|Phase|"
               r"Week|Day|Grade|Level|Study|Trial|Experiment|Exp|Model|Version)\b")
_SUPERSCRIPT ="¹²³⁰⁴-⁹"
_RANGE = r"\d{1,3}(?:\s*[,–-]\s*\d{1,3})*"

CITATION_MARKER = re.compile(
    "[" + _SUPERSCRIPT + "]"                                   # Unicode superscripts
    r"|<sup>\s*\d|\^\d+(?:[,–-]\d+)*\^"                    # HTML, Pandoc superscript
    r"|(?<=[A-Za-z)\]])[.,;:]\d{1,3}(?:[,–-]\d{1,3})*(?=\s|$)"  # AMA, flattened
    r"|\((?:refs?\.?\s*)?" + _RANGE + r"\)|\[" + _RANGE + r"\]"   # (12) (ref. 7) [1, 3]
    r"|\[\^[^\]\s]+\]|\[@[^\]\s]+"                              # footnote, Pandoc key
    r"|\\(?:cite[a-zA-Z]*|footnote)\s*[\[{]"                    # LaTeX
    r"|\[[A-Z][A-Za-z]{1,3}\+?\d{2}[a-z]?\]"                    # alpha key [Smi20]
    r"|\((?!" + _NOT_AUTHOR + r")[A-Z][\w'’-]+(?:\s+(?:and|&)\s+[A-Z][\w'’-]+)?"
    r"(?:\s+et al\.)?,?\s+\d{1,4}(?:[-–]\d+)?\)"           # (Jones 118)
    r"|\([^()]*\b" + _YEAR + r"\b[^()]*\)"                     # a year in parentheses
    r"|\b(?!" + _NOT_NAME + r")[A-Z][a-z]+(?:\s+et al\.)?,?\s+" + _YEAR + r"\b"
    r"|\bet al\.|https?://"
    r"|\b\d{1,4}\s+(?:[A-Z][A-Za-z]*\.\s?){1,4}(?:\d[a-z]{1,2}\s)?\d{1,5}\b"  # 998 F.3d 101
    r"|\[\d{4}\]\s+[A-Z]{2,}"                                  # [2021] UKSC 5
    r"|\baccording to\b(?!\s+(?:many\s+|some\s+|most\s+|the\s+)?"
    r"(?:experts|studies|research|scientists|sources)\b)")

# The writer's own evidence: a figure, table or supplementary reference, or a
# test statistic.
OWN_EVIDENCE = re.compile(
    r"(?i)\b(?:fig(?:ure)?s?\.?\s*S?\d|tables?\s+S?\d|suppl(?:ementary|\.))"
    r"|\bp\s*[=<>≤]\s*0?\.\d|\b\d{2}%\s*ci\b"
    r"|\b[tfrz]\s*(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?\s*=\s*-?\d*\.?\d")

LABEL = "authority appeal, no citation in the sentence"


def unanchored_appeals(sent, raw):
    """(start, end) of each appeal in `sent` that its sentence gives no source
    for. `raw` is the same sentence before any mask, at the same offsets."""
    if CITATION_MARKER.search(raw):
        return []
    own_ok = OWN_EVIDENCE.search(raw) is not None
    return [m.span() for m in AUTHORITY.finditer(sent) if not (m.group("own") and own_ok)]
