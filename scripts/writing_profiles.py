#!/usr/bin/env python3
"""writing_profiles.py -- the register-adaptive profile library, as data.

A profile is a register configuration (Halliday field/tenor/mode) expressed as a
rule record. The linter reads a record and never hard-codes a rule. Adding a
prose type is adding a record here, not editing the engine.

This scores the FORM of prose, never its substance or authenticity, and it never
tries to defeat AI detection. Those are non-goals, stated so no reader assumes
otherwise.

Standard library only.
"""
from __future__ import annotations

import re

SCHEMA_FIELDS = (
    "slop", "rigor", "max_sentence_words", "no_em_dash", "hedging", "voice",
    "eprime", "translation_ready", "readability_band", "output_format", "keep",
)

DEFAULT = "flavored"


class ProfileError(ValueError):
    """An unknown or malformed profile."""


# Terms of art the linter must never flag, whatever list they might collide with
# later. Kept here so every profile can share the base set.
_TERMS = (
    "pass", "fail", "undecided", "unverifiable", "candidate", "harness",
    "environment", "criterion", "receipt", "oracle", "certificate",
)


def _p(slop, rigor, *, max_words=None, no_em_dash=True, hedging="calibrated",
       voice="active-preferred", eprime=False, translation_ready=False,
       readability=(30, 70), output="markdown", keep=()):
    return {
        "slop": slop, "rigor": rigor, "max_sentence_words": max_words,
        "no_em_dash": no_em_dash, "hedging": hedging, "voice": voice,
        "eprime": eprime, "translation_ready": translation_ready,
        "readability_band": readability, "output_format": output,
        "keep": tuple(_TERMS) + tuple(keep),
    }


PROFILES: dict[str, dict] = {
    # The generic fallback profile_for() returns for an unmapped path. It must
    # exist as a real record, or load(DEFAULT) crashes on every unmapped file.
    "flavored": _p("flavored", "informal", output="any"),
    "procedure": _p("strict", "normative", max_words=20, hedging="banned",
                    voice="active-only", translation_ready=True, output="markdown"),
    "error-message": _p("strict", "normative", max_words=20, hedging="banned",
                         voice="active-only", output="plaintext"),
    "commit": _p("strict", "informal", max_words=50, hedging="banned",
                 voice="active-only", output="plaintext"),
    "changelog": _p("flavored", "informal", hedging="banned", output="markdown"),
    "release-notes": _p("flavored", "informal", output="markdown"),
    "api-docs": _p("flavored", "informal", voice="active-only",
                   translation_ready=True, output="markdown"),
    "normative-spec": _p("flavored", "normative", hedging="banned",
                         output="markdown", keep=("must", "should", "may",
                         "shall", "required", "recommended", "optional")),
    "research": _p("flavored", "calibrated", hedging="section-aware",
                   eprime=True, output="markdown"),
    "proof": _p("flavored", "structured", hedging="calibrated",
                output="latex", keep=("assume", "prove", "let", "qed")),
    "model-card": _p("flavored", "calibrated", output="markdown"),
    "readme": _p("flavored", "informal", output="markdown"),
    "legal": _p("flavored", "normative", voice="active-only", output="markdown"),
    "social": _p("flavored", "informal", output="plaintext"),
    "chat": _p("flavored", "calibrated", output="plaintext"),
    "narrative": _p("off", "informal", no_em_dash=False, hedging="calibrated",
                    voice="active-preferred", output="markdown"),
}

# First match wins. Patterns match the basename or a path fragment.
PATH_RULES: list[tuple[str, str]] = [
    (r"(?i)COMMIT_EDITMSG$", "commit"),
    (r"(?i)CHANGELOG(\.md)?$", "changelog"),
    (r"(?i)RELEASE[_-]?NOTES(\.md)?$", "release-notes"),
    (r"(?i)MODEL_CARD(\.md)?$", "model-card"),
    (r"(?i)(^|/)README(\.md)?$", "readme"),
    (r"\.tex$", "proof"),
    (r"\.lean$", "proof"),
    (r"(?i)/(specs?|rfc)/", "normative-spec"),
    (r"(?i)/(essays?|novels?|narrative)/", "narrative"),
    (r"(?i)/(papers?|research|whitepapers?)/", "research"),
    (r"(?i)/(legal|agreements?|contracts?)/", "legal"),
]


def load(name: str) -> dict:
    rec = PROFILES.get(name)
    if rec is None:
        raise ProfileError(
            f"unknown profile {name!r}; known: {', '.join(sorted(PROFILES))}")
    return dict(rec)


def profile_for(path: str) -> str:
    p = str(path).replace("\\", "/")
    for pattern, name in PATH_RULES:
        if re.search(pattern, p):
            return name
    return DEFAULT
