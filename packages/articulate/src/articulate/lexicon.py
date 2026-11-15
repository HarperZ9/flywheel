#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.lexicon -- the auxiliary regexes and word sets the scanner and the
advisories count over. Standard library only.
"""
import re

# Emoji: a coarse but serviceable set of the ranges frontier models reach for.
EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # symbols & pictographs, extended
    "\U00002600-\U000027BF"   # misc symbols + dingbats
    "\U0001F000-\U0001F0FF"   # tiles
    "\U00002B00-\U00002BFF"   # arrows/stars
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U00002190-\U000021FF"   # arrows (⇒ etc.)
    "\U00002700-\U000027BF"
    "]"
)

# Vague quantifier where a writer who knew the count would give it. Advisory,
# and suppressed when the same line already carries a digit (spec #23).
VAGUE_QUANT = re.compile(r"\b(?:various|numerous|a number of|several)\b", re.I)
DIGIT = re.compile(r"\d")
# "in order to": usually "to" does the same work, but usage guides accept it
# where it separates a purpose from a complement, so it is a LOW note and never
# blocks.
PADDED_PURPOSE = re.compile(r"\bin order to\b", re.I)
# "state of the art" is a term of art for the best published result, usually tied
# to a named benchmark. It is a LOW note only when its sentence carries no
# number, year or citation marker (the idea of the unsupported-authority
# lookahead, read over the whole sentence).
UNANCHORED_CLAIM = re.compile(r"\bstate[- ]of[- ]the[- ]art\b", re.I)
# Self-reference that announces what the text will do ("In this article, we
# will explore", "This post delves into") in place of doing it. A LOW note: a
# statement of content ("In this essay, I argue", "This article examines") raises
# nothing, since style guides model it as a thesis or scope statement.
_SELF_NOUN = (r"(?:essay|paper|thesis|dissertation|study|report|article|post|section|"
              r"chapter|piece|guide|work)")
_ANNOUNCE = r"(?:explore|discuss|look\s+at|delve(?:\s+into)?|dive\s+into|talk\s+about)"
ANNOUNCEMENT = re.compile(
    r"(?i)\bin\s+this\s+" + _SELF_NOUN + r",?\s+(?:we|i|you)"
    r"(?:['’]ll\s+|\s+(?:(?:will|shall|are\s+going\s+to|am\s+going\s+to|want\s+to|"
    r"would\s+like\s+to|aim\s+to|intend\s+to)\s+)?)" + _ANNOUNCE + r"\b"
    r"|\bthis\s+" + _SELF_NOUN + r"\s+(?:explores|delves\s+into|dives\s+into|will\s+"
    + _ANNOUNCE + r")\b")
# "with respect to": "on", "about" or "for" often does the same work, so it is a
# LOW note. It stays silent in the operator sense: after a derivative, gradient
# or similar term, or before a Greek letter, a subscripted symbol, a math span
# or a single letter other than "a" (a variable).
PADDED_PREPOSITION = re.compile(r"(?i)\bwith\s+respect\s+to\b")
OPERATOR_BEFORE = re.compile(r"(?i)\b(?:derivatives?|gradients?|partials?|integrals?|"
                             r"jacobians?|convex|continuous(?:ly)?|measurable|"
                             r"differentiable|invariant|integrable)\s+$")
OPERATOR_AFTER = re.compile(r"\s*(?:\$|\\[(\[]|[Ͱ-Ͽἀ-῿]|"
                            r"[A-Za-z]_|[b-zB-HJ-Z]\b(?!['’]))")
CLAIM_ANCHOR = re.compile(r"\d|https?://|\bet al\.|\\cite|\[@", re.I)

WORD = re.compile(r"\b\w+\b")
# Orwell/Williams structural signals, measured as document rates (length-
# independent, unlike raw type-token ratio, which is why TTR is not used here).
# The intensifiers are their own rule, so the adverb rate does not count them.
ADVERB = re.compile(r"\b(?!(?:really|actually|truly|genuinely)\b)\w{3,}ly\b", re.I)
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+ed\b(?!\s+by\b)", re.I)
# Keyword-free contrast pair / negative parallelism: two short adjacent sentences
# with the same subject where one affirms and the next negates ("You can watch
# what a model does. You cannot watch what it is."). The antithesis regex misses
# this because there is no "not X but Y" keyword to anchor on.
NEG = re.compile(r"\b(?:cannot|can ?not|can't|is ?n't|is not|are ?n't|are not|"
                 r"does ?n't|does not|do ?n't|do not|will not|won't|never|"
                 r"no longer|not)\b", re.I)
FIRSTWORD = re.compile(r"^\W*(\w+)")

# Williams, "Style: Lessons in Clarity and Grace" (the basis Ptacek names).
# Expletive opener: "it is important / worth / crucial / essential / necessary /
# vital" at a sentence start, or after one leading clause and a comma, is
# metadiscourse that delays the subject. A default LOW note that never blocks,
# matched on the stripped-markup sentence start; group 1 is the reported span.
# It is the only rule on this opener: the MEDIUM throat-clearing and
# worth-noting rules no longer match it, so one span gets one finding.
EXPLETIVE = re.compile(r"(?i)^(?:[^,.;:!?\n]{1,80},\s+)?"
                       r"(it(?:['’]s|\s+is|\s+was)\s+"
                       r"(?:important|worth|crucial|essential|necessary|vital)\b)")
# Existential "there is / are / was / were" is grammatical and often the
# clearest phrasing, so it is a house note, shown only on request.
EXISTENTIAL = re.compile(r"(?i)^there (?:is|are|was|were)\b")
# Nominalization: action buried in an abstract noun. Advisory, and only when
# several stack in one line, because this domain uses "verification",
# "evaluation", "attribution" as real terms.
NOMINAL = re.compile(r"\b\w{4,}(?:tion|ment|ance|ence|ancy|ency)\b", re.I)

# Structural-heuristic constants (comprehensive set). Markdown structure markers
# and the token sets the statistical advisories count over. These feed report-only
# LOW advisories and the local-anaphora MEDIUM, never the HIGH device gate.
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
BOLD_SPAN = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
# Stopword-only n-grams are not repetition signals, so they are excluded.
NGRAM_STOP = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "as", "at", "by", "is", "are", "was", "were", "be", "been", "it", "its",
    "this", "that", "these", "those", "you", "we", "they", "i", "he", "she",
    "from", "into", "than", "then", "so", "if", "not", "no", "do", "does",
    "can", "will", "would", "your", "our", "their", "there", "here", "which",
})
# Hedge tokens; several in one sentence is a hedge cluster (Orwell caution excess).
HEDGE_WORDS = re.compile(r"(?i)\b(?:may|might|could|can|perhaps|possibly|potentially|"
                         r"likely|probably|maybe|generally|typically|usually|often|"
                         r"somewhat|arguably|seemingly|presumably|conceivably)\b")

# Function-word sentence openers everyone reuses; excluded from opener-variety.
OPENER_STOP = {
    "the", "a", "an", "it", "this", "that", "these", "those", "there", "in",
    "on", "for", "and", "but", "so", "to", "as", "we", "you", "i", "they",
    "he", "she", "its", "their", "our", "his", "her", "at", "of", "by", "with",
    "from", "or", "if", "when", "while", "then", "now", "here", "no", "one",
    "each", "every", "some", "most", "all", "both", "what", "how", "why",
}
