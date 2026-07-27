#!/usr/bin/env python3
"""writing_lists.py -- the slop word lists, as data with one home.

Moved out of check_writing.py so the engine file stays under the 300-line gate
as Phase 2 checks land. These lists are exactly the ones the Phase 1 engine
shipped with; moving them changed no entry.

Standard library only.
"""
from __future__ import annotations

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
