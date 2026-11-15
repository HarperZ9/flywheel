"""The structure rule pack (profiles `chat` and the house voice): sentence
shapes a line-by-line check passes, read a paragraph at a time.

  structure-anaphora   sentences in a row that open with the same word: two
                       report (LOW), three or more gate (HIGH).
  structure-parallel   three sentences in one paragraph on one frame (HIGH).
  structure-triad      three parallel sentences in a row (HIGH), or a
                       three-item list of short phrases (LOW).
  structure-pin        a paragraph opener that only announces the paragraph
                       (HIGH with a pointing phrase, MEDIUM for a bare label).
  structure-parataxis  three or more short unlinked statements in a row
                       (HIGH), or a stub statement in an unlinked paragraph
                       (MEDIUM).
  structure-pointer    a sentence that only rates another sentence or the
                       text before it (HIGH), or a short labelling beat
                       (MEDIUM).
  structure-landing    a closing sentence that hands the step back (HIGH), or
                       a short one-clause closer (MEDIUM).

The pack runs only under a profile that lists it. A profile for an author's
own voice (`author-voice`, `narrative`) does not, so deliberate anaphora in a
person's own text raises nothing here. The rules read shape and a closed set
of phrases: they miss a paraphrase and they fire on a writer who uses the
shape on purpose. docs/structure-rules.md gives the measured rates.
Standard library only.
"""
from __future__ import annotations

from . import structure_moves, structure_runs
from . import structure_text as T

NAME = "structure"
CATEGORIES = ("structure-anaphora", "structure-parallel", "structure-triad", "structure-pin",
              "structure-parataxis", "structure-pointer", "structure-landing")
OPTIONS = {}
_DETECTORS = (structure_runs.anaphora, structure_runs.parallel, structure_runs.triad,
              structure_moves.pin, structure_runs.parataxis, structure_moves.pointer,
              structure_moves.landing)


# A list item is a sentence or a short paragraph for the rules that judge one
# sentence by its place. The run rules stay out of lists.
_ITEM_DETECTORS = (structure_moves.pin, structure_moves.pointer, structure_moves.landing)


def scan(text, prose, opts, make):
    found = {"HIGH": [], "MEDIUM": [], "LOW": []}
    seen = set()
    for units, detectors in ((T.list_items(prose), _ITEM_DETECTORS),
                             (T.paragraphs(prose), _DETECTORS)):
        for unit in units:
            for detect in detectors:
                for tier, items in detect(unit, text, make).items():
                    for f in items:
                        # One span is reported once for a category, whichever
                        # reading reached it first.
                        key = (f["category"], f["start"], f["end"])
                        if key not in seen:
                            seen.add(key)
                            found[tier].append(f)
    for tier in found:
        found[tier].sort(key=lambda f: (f["start"], f["category"]))
    return found


def cadence(prose):
    """The local opener measure. The detector's `repetitive_openers` is a
    whole-document ratio over content-word openers and needs twelve of them,
    so three sentences in a row that open with "One" leave it False. This
    counts the longest run of consecutive sentences that share an opener."""
    run = structure_runs.longest_opener_run(T.paragraphs(prose))
    return {"longest_opener_run": run, "repeated_openers_in_a_row": run >= 3}


def fingerprint():
    return structure_runs.fingerprint() + structure_moves.fingerprint()
