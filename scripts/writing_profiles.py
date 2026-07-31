#!/usr/bin/env python3
"""writing_profiles.py -- the register-adaptive profile library, as data.

A profile is a register configuration (Halliday field/tenor/mode) expressed as a
rule record. The linter reads thresholds and toggles from the record; the shared
word lists live in writing_lists, and the hard/soft split is itself profile data
(each record's hard tuple, seeded from writing_lists.HARD_DEFAULTS). Adding a
prose type is adding a record here, not editing the engine.

This scores the FORM of prose, never its substance or authenticity, and it never
tries to defeat AI detection. Those are non-goals, stated so no reader assumes
otherwise.

Standard library only.
"""
from __future__ import annotations

import re

import writing_lists

# PHASE 4 HONESTY NOTE. Every schema field now carries shipped semantics:
# eight drive the linter (slop, hard, keep, no_em_dash, max_sentence_words,
# eprime, readability_band, hedging), register is provenance, and four drive
# the /ste rewrite rather than the linter (rigor, voice, translation_ready,
# output_format; the skill documents the mapping). Nothing on this schema is
# inert, and nothing is deferred.
#
# PHASE 3 NOTE. hard joins the schema: the block-versus-report split is now
# profile data (writing_lists.HARD_DEFAULTS), not engine code. A profile that
# omits hard gets its slop level's default; a profile may narrow or widen its
# own tuple. load() validates every hard tuple against writing_lists'
# KNOWN_CATEGORIES / REPORT_ONLY_CATEGORIES so a misconfigured gate refuses
# rather than silently gating wrong.
SCHEMA_FIELDS = (
    "slop", "rigor", "max_sentence_words", "no_em_dash", "hedging", "voice",
    "eprime", "translation_ready", "readability_band", "output_format", "keep",
    "register", "hard",
)

DEFAULT = "flavored"


class ProfileError(ValueError):
    """An unknown or malformed profile."""


# Terms of art the linter must never flag, whatever list they might collide with
# later. Kept here so every profile can share the base set. keep is exact-form:
# keeping a word does not keep its inflections; list each form you mean.
_TERMS = (
    "pass", "fail", "undecided", "unverifiable", "candidate", "harness",
    "environment", "criterion", "receipt", "oracle", "certificate",
)


def _p(slop, rigor, *, max_words=None, no_em_dash=True, hedging="calibrated",
       voice="active-preferred", eprime=False, translation_ready=False,
       readability=(30, 70), output="markdown", keep=(),
       register=("general", "peer", "written"), hard=None):
    return {
        "slop": slop, "rigor": rigor, "max_sentence_words": max_words,
        "no_em_dash": no_em_dash, "hedging": hedging, "voice": voice,
        "eprime": eprime, "translation_ready": translation_ready,
        "readability_band": readability, "output_format": output,
        "keep": tuple(_TERMS) + tuple(keep),
        "register": {"field": register[0], "tenor": register[1],
                     "mode": register[2]},
        "hard": tuple(hard) if hard is not None
                else tuple(writing_lists.HARD_DEFAULTS[slop]),
    }


PROFILES: dict[str, dict] = {
    # The generic fallback profile_for() returns for an unmapped path. It must
    # exist as a real record, or load(DEFAULT) crashes on every unmapped file.
    "flavored": _p("flavored", "informal", output="any"),
    "procedure": _p("strict", "normative", max_words=20, hedging="banned",
                    voice="active-only", translation_ready=True, output="markdown",
                    register=("operations", "operator-instruction",
                              "numbered-steps")),
    "error-message": _p("strict", "normative", max_words=20, hedging="banned",
                         voice="active-only", output="plaintext"),
    "commit": _p("strict", "informal", max_words=50, hedging="banned",
                 voice="active-only", output="plaintext"),
    "changelog": _p("flavored", "informal", hedging="banned", output="markdown",
                    hard=writing_lists.HARD_DEFAULTS["flavored"]
                    + ("unreferenced_entry",)),
    "release-notes": _p("flavored", "informal", output="markdown"),
    "api-docs": _p("flavored", "informal", voice="active-only",
                   translation_ready=True, output="markdown"),
    "normative-spec": _p("flavored", "normative", hedging="banned",
                         output="markdown", keep=("must", "should", "may",
                         "shall", "required", "recommended", "optional")),
    "research": _p("flavored", "calibrated", hedging="section-aware",
                   eprime=True, output="markdown",
                   register=("findings", "peer-review", "written-argument")),
    "proof": _p("flavored", "structured", hedging="calibrated",
                output="latex", keep=("assume", "prove", "let", "qed")),
    "model-card": _p("flavored", "calibrated", output="markdown"),
    "readme": _p("flavored", "informal", output="markdown"),
    "legal": _p("flavored", "normative", voice="active-only", output="markdown"),
    "social": _p("flavored", "informal", output="plaintext"),
    "chat": _p("flavored", "calibrated", output="plaintext",
               register=("engineering", "operator-dialogue", "conversational")),
    "narrative": _p("off", "informal", no_em_dash=False, hedging="calibrated",
                    voice="active-preferred", output="markdown",
                    register=("story", "reader", "literary")),
}

# First match wins. Patterns match the basename or a path fragment.
PATH_RULES: list[tuple[str, str]] = [
    # Filename rules carry a (^|/) boundary so "notCHANGELOG.md" is not a
    # changelog. The extension rules are case-insensitive like the rest.
    (r"(?i)(^|/)COMMIT_EDITMSG$", "commit"),
    (r"(?i)(^|/)CHANGELOG(\.md)?$", "changelog"),
    (r"(?i)(^|/)RELEASE[_-]?NOTES(\.md)?$", "release-notes"),
    (r"(?i)(^|/)MODEL_CARD(\.md)?$", "model-card"),
    (r"(?i)(^|/)README(\.md)?$", "readme"),
    (r"(?i)\.tex$", "proof"),
    (r"(?i)\.lean$", "proof"),
    (r"(?i)(^|/)(specs?|rfc)/", "normative-spec"),
    (r"(?i)(^|/)(essays?|novels?|narrative)/", "narrative"),
    (r"(?i)(^|/)(papers?|research|whitepapers?)/", "research"),
    (r"(?i)(^|/)(legal|agreements?|contracts?)/", "legal"),
]


def load(name: str) -> dict:
    rec = PROFILES.get(name)
    if rec is None:
        raise ProfileError(
            f"unknown profile {name!r}; known: {', '.join(sorted(PROFILES))}")
    bad = set(rec["hard"]) - writing_lists.KNOWN_CATEGORIES
    smuggled = set(rec["hard"]) & set(writing_lists.REPORT_ONLY_CATEGORIES)
    if bad or smuggled:
        raise ProfileError(
            f"profile {name!r} carries an invalid hard tuple: "
            f"unknown={sorted(bad)} report_only={sorted(smuggled)}")
    # Shallow copy is safe only while every schema value stays immutable
    # (scalars and tuples). A list or dict field would alias through this.
    return dict(rec)


def profile_for(path: str) -> str:
    p = str(path).replace("\\", "/")
    for pattern, name in PATH_RULES:
        if re.search(pattern, p):
            return name
    return DEFAULT


_DECLARED = re.compile(r"^\s*(?:<!--\s*)?writing-profile:\s*([a-z][a-z-]*)",
                       re.MULTILINE)


def declared_profile(text: str) -> "str | None":
    """A writing-profile tag in the first 10 lines, or None. The override is
    explicit authorial intent, so it outranks path inference and loses only to
    a --profile flag."""
    head = "\n".join(text.splitlines()[:10])
    m = _DECLARED.search(head)
    return m.group(1) if m else None
