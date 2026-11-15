#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.profiles -- the register-adaptive profile system.

Ported from the flywheel writing_lint profile library and adapted to drive the
Articulate detector's precision tiers. A profile is a register configuration
(Halliday field/tenor/mode) expressed as data: it sets a `slop` level that
decides which detector tiers hard-gate, a `keep` list of terms of art the
detector must never flag, and provenance fields. Adding a prose type is adding a
record here, not editing the engine.

This scores the FORM of prose, never its substance or authenticity, and it never
tries to defeat AI detection. Those are non-goals, stated so no reader assumes
otherwise.

The detector's vocabulary is its own regex pattern set, so the flywheel word
lists (and their en-GB false positives like `whilst`/`amongst`) are not carried
over. Standard library only.
"""
from __future__ import annotations

import re

DEFAULT = "flavored"

# slop level -> which detector tiers block. Mirrors detector.GATE_TIERS; the
# detector is the authority, this is the human-readable statement of it.
#   off       nothing gates (report only): narrative, literary essays
#   flavored  the HIGH device tier gates: docs, research, chat, readme
#   strict    HIGH + MEDIUM gate: procedures, commits, error messages, essays
#             that must be device-free


class ProfileError(ValueError):
    """An unknown or malformed profile."""


# Terms of art the detector must never flag, whatever list they might collide
# with. Shared base set; `keep` is exact-form (an inflection is a separate entry).
_TERMS = (
    "pass", "fail", "undecided", "unverifiable", "candidate", "harness",
    "environment", "criterion", "receipt", "oracle", "certificate",
    "match", "drift", "substrate", "load-bearing",
)


def _p(slop, *, keep=(), no_em_dash=True, max_words=None,
       register=("general", "peer", "written")):
    return {
        "slop": slop,
        "keep": tuple(_TERMS) + tuple(keep),
        "no_em_dash": no_em_dash,
        "max_sentence_words": max_words,
        "register": {"field": register[0], "tenor": register[1], "mode": register[2]},
    }


PROFILES: dict[str, dict] = {
    "flavored": _p("flavored"),
    "procedure": _p("strict", max_words=20,
                    register=("operations", "operator-instruction", "numbered-steps")),
    "error-message": _p("strict", max_words=20),
    "commit": _p("strict", max_words=50),
    "changelog": _p("flavored"),
    "release-notes": _p("flavored"),
    "api-docs": _p("flavored"),
    "normative-spec": _p("flavored",
                         keep=("must", "should", "may", "shall", "required",
                               "recommended", "optional")),
    # Formal Latinate words that are ordinary in scholarly writing; kept in the
    # research register so a paper is not flagged for its normal vocabulary. The
    # stems match every inflection through the substring allowlist. This is a
    # register call and carries no fairness claim; a "fairer to non-native
    # writers" claim waits on a labeled corpus run through bench.py.
    "research": _p("flavored",
                   register=("findings", "peer-review", "written-argument"),
                   keep=("utiliz", "utilis", "facilitat", "comprehensive")),
    # A pure-proof register. The keep-list clears ordinary rigor vocabulary that
    # the register tells would otherwise flag: analytic and geometric idioms plus
    # the research Latinate stems. The banned HIGH devices still gate; a proof
    # rephrases them. This screens prose only and says nothing about a theorem's truth.
    "proof": _p("flavored",
                keep=("assume", "prove", "let", "qed", "theorem", "lemma",
                      "corollary", "proposition", "hypothesis", "monotone",
                      "compact", "bounded", "at scale", "surface area", "crux",
                      "utiliz", "utilis", "facilitat", "comprehensive")),
    "model-card": _p("flavored"),
    "readme": _p("flavored"),
    "legal": _p("flavored"),
    "journalism": _p("flavored",
                     register=("news", "public", "reported"),
                     keep=("said", "according", "confirmed", "reported")),
    "social": _p("flavored"),
    "chat": _p("flavored",
               register=("engineering", "operator-dialogue", "conversational")),
    # Essays in this program are device-free, so an
    # essay uses the strict slop level; the register map's usual "off" applies
    # only to literary narrative (fiction), where authorial voice governs.
    "essay": _p("strict", register=("argument", "reader", "written-argument")),
    "narrative": _p("off", no_em_dash=False,
                    register=("story", "reader", "literary")),
}

# First match wins. Patterns match the basename or a path fragment.
PATH_RULES: list[tuple[str, str]] = [
    (r"(?i)(^|/)COMMIT_EDITMSG$", "commit"),
    (r"(?i)(^|/)CHANGELOG(\.md)?$", "changelog"),
    (r"(?i)(^|/)RELEASE[_-]?NOTES(\.md)?$", "release-notes"),
    (r"(?i)(^|/)MODEL_CARD(\.md)?$", "model-card"),
    (r"(?i)(^|/)README(\.md)?$", "readme"),
    # A .tex under a proofs/ or papers/ tree is math and belongs in a math register,
    # so it routes there ahead of the .tex-is-essay default. An essay written in
    # .tex (device-free essays) still lands on essay.
    (r"(?i)(^|/)(proofs?)/", "proof"),
    (r"(?i)(^|/)(papers?|research|whitepapers?)/", "research"),
    (r"(?i)\.tex$", "essay"),
    (r"(?i)\.fountain$", "screenplay"),
    (r"(?i)(^|/)(specs?|rfc)/", "normative-spec"),
    (r"(?i)(^|/)(poems?|poetry|verse)/", "poetry"),
    (r"(?i)(^|/)(screenplays?|scripts?/screenplay)/", "screenplay"),
    (r"(?i)(^|/)(memoirs?)/", "memoir"),
    (r"(?i)(^|/)(novels?|fiction|stories)/", "narrative"),
    (r"(?i)(^|/)(essays?|blog|writing)/", "essay"),
    (r"(?i)(^|/)(papers?|research|whitepapers?)/", "research"),
    (r"(?i)(^|/)(legal|agreements?|contracts?)/", "legal"),
]


def load(name: str) -> dict:
    rec = PROFILES.get(name)
    if rec is None:
        # A genre id is a profile too: it carries slop, keep, and register plus
        # the genre fields. Deferred import breaks the profiles<->genres cycle.
        from . import genres
        if name in genres.GENRES:
            return genres.load(name)
        raise ProfileError(
            f"unknown profile {name!r}; known: "
            f"{', '.join(sorted(PROFILES) + sorted(genres.GENRES))}")
    return dict(rec)


def profile_for(path: str) -> str:
    p = str(path).replace("\\", "/")
    for pattern, name in PATH_RULES:
        if re.search(pattern, p):
            return name
    return DEFAULT


_DECLARED = re.compile(r"^\s*(?:<!--\s*|%\s*)?writing-profile:\s*([a-z][a-z-]*)",
                       re.MULTILINE)


def declared_profile(text: str):
    """A `writing-profile:` tag in the first 10 lines, or None. Explicit authorial
    intent, so it outranks path inference and loses only to an explicit choice."""
    head = "\n".join(text.splitlines()[:10])
    m = _DECLARED.search(head)
    return m.group(1) if m else None


def resolve(path=None, text=None, override=None) -> dict:
    """Pick a profile: explicit override, else an in-file tag, else path inference,
    else the default. Returns the loaded profile dict."""
    if override:
        return load(override)
    if text is not None:
        tag = declared_profile(text)
        if tag:
            return load(tag)
    if path is not None:
        return load(profile_for(path))
    return load(DEFAULT)
