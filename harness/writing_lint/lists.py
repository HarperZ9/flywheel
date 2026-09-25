#!/usr/bin/env python3
"""writing_lists.py -- the slop word lists, as data with one home.

Moved out of check_writing.py so the engine file stays under the 300-line gate
as Phase 2 checks land. These lists are exactly the ones the Phase 1 engine
shipped with; moving them changed no entry. Phase 3 added the report-check
patterns and the gate data (HARD_DEFAULTS, KNOWN_CATEGORIES,
REPORT_ONLY_CATEGORIES); Phase 4 added HEDGE_WORDS.

Standard library only.
"""
from __future__ import annotations

import re

MARKETING = (
    "seamless", "seamlessly", "robust", "powerful", "cutting-edge", "effortless",
    "effortlessly", "world-class", "next-generation", "revolutionary", "blazing",
    "lightning-fast", "elegant", "delightful", "turnkey", "best-in-class",
    "state-of-the-art", "game-changing", "first-class", "battle-tested",
    "enterprise-grade", "supercharge", "unlock", "unleash", "empower", "empowers",
)
BANNED = (
    "commence", "commences", "initiate", "initiates", "utilize", "utilizes",
    "utilizing", "leverage", "leverages", "leveraging", "facilitate",
    "facilitates", "prior to", "subsequent to", "obtain", "obtains", "acquire",
    "acquires", "additionally", "furthermore", "moreover", "comprehensive",
    "aforementioned", "henceforth", "therein", "whilst", "amongst", "numerous",
    "myriad", "plethora", "in order to", "a variety of", "in the event that",
    "due to the fact that",
)
PHRASAL = (
    "spin up", "spin down", "reach out", "dive into", "dives into", "diving into",
    "kick off", "kicks off", "roll out", "rolls out", "circle back", "drill down",
)
MODAL_HEDGE = (
    "it is important to note", "it should be noted", "it is worth noting",
    "please note that", "as mentioned", "as noted above",
)
# Uncertainty words a hedging="banned" profile refuses. This is DISTINCT from
# MODAL_HEDGE (filler phrases, banned in flavored prose too): these words are
# legitimate calibrated uncertainty in research or chat registers and are
# refused only where hedging itself is banned, such as procedures.
HEDGE_WORDS = (
    "might", "perhaps", "possibly", "probably", "maybe", "likely", "unlikely",
    "could", "arguably", "seemingly", "somewhat",
)

BE = r"(?:am|is|are|was|were|be|been|being)"
PP_IRREG = (r"(?:done|made|sent|read|built|kept|held|set|put|run|written|"
            r"shown|given|taken|found|got|gotten|seen|known|thrown|drawn)")
PASSIVE = re.compile(rf"\b{BE}\s+(?:\w+ed|{PP_IRREG})\b", re.IGNORECASE)
ING_MAIN = re.compile(rf"\b{BE}\s+\w+ing\b", re.IGNORECASE)
NOMINAL = re.compile(
    r"\b(?:perform|performs|conduct|conducts|carry out|carries out|"
    r"make use of|makes use of)\b"
    r"|\b\w+(?:tion|ment|ance|ence)s?\s+of\b", re.IGNORECASE)
# Ordinary "of" phrases are fine; only a nominalizing suffix directly before
# "of" counts, which is why "top of the file" passes and "utilization of"
# does not.

# The gate, as data. HARD_DEFAULTS seeds each profile's hard tuple by slop
# level; a profile may narrow or widen its own tuple. REPORT_ONLY_CATEGORIES
# may never appear in any hard tuple, and KNOWN_CATEGORIES is the closed set a
# hard tuple may draw from: both rules are enforced with ProfileError, because
# a gate misconfigured in data must refuse, not silently gate wrong.
HARD_DEFAULTS = {
    "strict": ("banned_word", "contraction", "em_dash", "hedge_word",
               "long_sentence", "marketing_adjective", "modal_hedge",
               "phrasal_verb", "semicolon"),
    "flavored": ("banned_word", "em_dash", "marketing_adjective",
                 "modal_hedge", "phrasal_verb"),
    "off": (),
}
REPORT_ONLY_CATEGORIES = ("passive_voice", "ing_main_verb", "nominalization",
                          "long_paragraph", "be_verb", "rule_of_three",
                          "corrective_negation", "negative_anaphora",
                          "landing_sentence",
                          # Higher-order (Articulate next-layer) tells. Each
                          # operationalizes a rule the STE standard already
                          # states; each is report-only and never gates.
                          "parallel_enumeration", "aphoristic_landing",
                          "repeated_syntactic_frame", "specificity_floor",
                          "rhythm_variance")
KNOWN_CATEGORIES = frozenset(
    ("em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
     "modal_hedge", "contraction", "semicolon", "long_sentence",
     "hedge_word", "unreferenced_entry") + REPORT_ONLY_CATEGORIES)

# -- Lexicons for the higher-order structural detectors (higher_order.py) --
# A coarse, stdlib-only part-of-speech backbone. It is deliberately shallow: it
# separates function words from content words and spots verb-led vs noun-led
# enumeration. It is not a tagger, and every detector that reads it is
# report-only, so a misread informs rather than gates.
DETERMINERS = frozenset((
    "a", "an", "the", "this", "that", "these", "those", "my", "your", "our",
    "their", "its", "his", "her", "some", "any", "no", "every", "each", "all",
    "both", "another", "such", "one",
))
PREPOSITIONS = frozenset((
    "of", "in", "on", "at", "to", "for", "with", "from", "by", "as", "into",
    "over", "under", "about", "between", "through", "without", "within",
    "across", "after", "before", "during", "against", "toward", "towards",
    "upon", "onto", "per", "via",
))
PRONOUNS = frozenset((
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "us", "them",
    "who", "whom", "whose", "which", "one", "none", "someone", "anyone",
    "everyone", "nobody", "people", "something", "anything",
))
CONJUNCTIONS = frozenset((
    "and", "or", "but", "so", "yet", "nor", "because", "although", "though",
    "while", "whereas", "if", "when", "where", "since", "unless", "until",
    "whether", "than", "as",
))
AUX_BE = frozenset((
    "am", "is", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "have", "has", "had", "can", "could", "will", "would", "shall",
    "should", "may", "might", "must",
))
WH_WORDS = frozenset((
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
))
# Common verb bases and a few frequent inflections. Suffix rules (-ed, -ing)
# extend this at read time, so the set only carries forms the suffix rules miss.
ENUM_VERBS = frozenset((
    "price", "read", "flag", "sort", "grade", "run", "runs", "build", "builds",
    "check", "checks", "verify", "measure", "ship", "score", "draft", "review",
    "hold", "holds", "help", "helps", "record", "records", "emit", "emits",
    "recompute", "reproduce", "reproduces", "prove", "proves", "move", "moves",
    "give", "gives", "take", "takes", "ask", "asks", "keep", "keeps", "walk",
    "reach", "reaches", "produce", "produces", "affect", "affects", "deploy",
    "install", "break", "decide", "decides", "pass", "adopt", "capture",
    "inspect", "trust", "describe", "choose", "feed", "feeds", "get", "gets",
    "sort", "grade", "map", "maps", "cut", "cuts", "add", "adds", "find",
    "finds", "make", "makes", "set", "sets", "use", "uses", "write", "writes",
    "test", "tests", "sell", "buy", "clear", "close", "open", "start", "stop",
    "load", "save", "sign", "send", "watch", "guard", "gate", "route", "parse",
))
# Words that never count as a "content word" for landing-sentence overlap. The
# union of the function-word sets above plus a thin layer of light verbs.
STOPWORDS = (DETERMINERS | PREPOSITIONS | PRONOUNS | CONJUNCTIONS | AUX_BE
             | WH_WORDS | frozenset((
                 "not", "no", "nor", "very", "just", "only", "also", "even",
                 "then", "now", "here", "there", "out", "up", "down", "off",
                 "more", "most", "less", "least", "much", "many", "few", "own",
                 "same", "other", "into", "about", "still", "yet",
             )))
# Aphoristic closers: the short "and that is the point" beat that seals a
# machine-shaped paragraph. Matched as a phrase anywhere for the tag branch.
LANDING_TAGS = (
    "and that is the point", "that is the point", "that is exactly right",
    "is where the harm collects", "that is what matters", "and that matters",
    "this is the crux", "that is the whole point", "which is the point",
    "that is the tell", "and that is the tell", "and it marks the boundary",
    "it marks the boundary", "and that is precisely the point",
    "that is the heart of it", "and that is enough",
)
# Unsourced authority: an appeal to unnamed evidence or vague recency.
UNSOURCED_AUTHORITY = (
    "a reviewer wrote", "reviewers wrote", "a reviewer noted", "studies show",
    "research shows", "studies have shown", "experts say", "experts agree",
    "it is well known", "it is widely known", "observers note", "critics say",
    "many believe", "some argue", "it is often said", "recent work shows",
    "recently",
)
# Unquantified magnitude: a size claim with no denominator or interval.
UNQUANTIFIED_MAGNITUDE = (
    "tens of thousands", "hundreds of thousands", "millions of", "a great deal",
    "countless", "a number of", "a variety of", "a range of", "many", "several",
    "various", "numerous", "a handful of", "vast", "enormous", "massive",
)
