#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.genres -- the genre axis for narrative and expressive prose.

A register profile answers "what is this document's field, tenor, mode". A genre
answers a different question: is this literary fiction, category fiction, a young
adult novel, a screenplay, a poem, or a memoir. Each genre reads by its own
conventions, so a scanner tuned for an essay misreads a novel. This module adds
that axis as data. Adding a genre is adding one record here, not editing the
scanner.

A genre record carries the register base it builds on plus a few genre fields the
detector consumes:

  slop                 which precision tiers gate. Fiction and verse sit at
                       "off": authorial voice governs and nothing blocks. A
                       screenplay sits at "flavored" so the banned devices still
                       gate on action lines, where economy is the craft rule.
  unit                 "sentence" by default, or "line" for verse, where a line
                       break is the unit and sentence-length cadence does not apply.
  structural_classify  "fountain" for a screenplay: each line is typed by role
                       (slug, action, cue, parenthetical, dialogue) before any
                       prose rule runs, so only action faces device scrutiny.
  dialogue_exempt      mask quoted speech before the device passes, so a
                       character's line is read in the character's voice and is
                       never scored as the author's own prose.
  quote_exempt_all     the stricter memoir rule: quoted testimony is excluded
                       from every category, because those quotes are often
                       recalled and rescoring or rewriting them is a factual error.
  fiction_slop         run the report-only fiction lexicon (generation artifacts
                       such as the somatic cliche). It is an advisory, never a gate.
  suppress_categories  craft-device categories a genre removes from the report
                       outright, because they name legitimate technique in that
                       genre. Verse removes antithesis, the triad, the contrast
                       pair, and the cadence signal.

The lexicon and every genre default here score the FORM of prose against genre
convention. They never judge whether the writing is authentic, and they never
try to defeat AI detection. Standard library only.
"""
from __future__ import annotations

from . import profiles

# Craft devices that read as flaws in an essay but are ordinary technique in
# verse (chiasmus, the triad, anaphora, the turned line). Removed from the
# poetry report so the tool does not flag a poet for writing a poem.
_VERSE_DEVICE_SUPPRESS = (
    "antithesis", "corrective-negation", "substitution", "negative-parallel",
    "contrast-pair", "cadence", "rule-of-three", "anaphora",
    "fragment-opener", "imperative-pair",
)


class GenreError(ValueError):
    """An unknown or malformed genre."""


def _g(base, *, slop="off", unit="sentence", structural_classify=None,
       dialogue_exempt=True, quote_exempt_all=False, fiction_slop=True,
       suppress_categories=(), keep=()):
    return {
        "base": base,
        "slop": slop,
        "unit": unit,
        "structural_classify": structural_classify,
        "dialogue_exempt": dialogue_exempt,
        "quote_exempt_all": quote_exempt_all,
        "fiction_slop": fiction_slop,
        "suppress_categories": tuple(suppress_categories),
        "keep": tuple(keep),
    }


GENRES: dict[str, dict] = {
    # Literary fiction: voice carries the work, so the device tiers report but
    # never gate; the fiction lexicon stays on as an advisory.
    "literary-fiction": _g("narrative"),
    # Category fiction: as literary, plus convention phrasing the genres lean on,
    # kept so the register pass does not flag a working romance or thriller line.
    "genre-fiction": _g(
        "narrative",
        keep=("heartbeat", "breathless", "smoldering", "chiseled", "ravish",
              "shadowy", "detective", "suspect", "alibi", "the killer",
              "starship", "hyperdrive", "the realm", "sorcerer", "prophecy")),
    # Young adult: same posture as literary fiction; a distinct id so a house can
    # route its YA list to its own record later.
    "ya-fiction": _g("narrative"),
    # Memoir and creative nonfiction: the interiority a journalism profile would
    # flag is the form here, so it stays at "off". Recalled quotes are excluded
    # from every category, stricter than a reported quote in the news.
    "memoir": _g("narrative", quote_exempt_all=True),
    # Screenplay: Fountain roles are classified first. Action lines keep the
    # banned-device gate (present-tense, filmable economy); dialogue is exempt
    # and carries only the fiction lexicon as an advisory.
    "screenplay": _g("narrative", slop="flavored", structural_classify="fountain",
                     dialogue_exempt=False),
    # Poetry: the line is the unit, the craft-device categories are removed from
    # the report, and the fiction lexicon runs only as a low-confidence advisory.
    # The tool makes no claim to detect AI in verse: readers cannot either.
    "poetry": _g("narrative", unit="line",
                 suppress_categories=_VERSE_DEVICE_SUPPRESS),
}


def load(genre_id: str) -> dict:
    """Resolve a genre to a profile-like dict the detector consumes: slop, keep,
    register, plus the genre fields. Fails closed on an unknown genre."""
    g = GENRES.get(genre_id)
    if g is None:
        raise GenreError(
            f"unknown genre {genre_id!r}; known: {', '.join(sorted(GENRES))}")
    base = profiles.load(g["base"])
    return {
        "slop": g["slop"],
        "keep": tuple(base.get("keep", ())) + g["keep"],
        "register": base.get("register"),
        "genre": genre_id,
        "unit": g["unit"],
        "structural_classify": g["structural_classify"],
        "dialogue_exempt": g["dialogue_exempt"],
        "quote_exempt_all": g["quote_exempt_all"],
        "fiction_slop": g["fiction_slop"],
        "suppress_categories": g["suppress_categories"],
    }


def names():
    return sorted(GENRES)
