#!/usr/bin/env python3
"""writing_lists.py -- the slop word lists, as data with one home.

Moved out of check_writing.py so the engine file stays under the 300-line gate
as Phase 2 checks land. These lists are exactly the ones the Phase 1 engine
shipped with; moving them changed no entry.

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
    "could", "should perhaps", "arguably", "seemingly", "somewhat",
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
                          "long_paragraph", "be_verb")
KNOWN_CATEGORIES = frozenset(
    ("em_dash", "marketing_adjective", "banned_word", "phrasal_verb",
     "modal_hedge", "contraction", "semicolon", "long_sentence",
     "hedge_word", "unreferenced_entry") + REPORT_ONLY_CATEGORIES)
