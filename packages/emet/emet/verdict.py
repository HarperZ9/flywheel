#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""verdict.py - the closed verdict lattice, made STRUCTURAL (Boundary 1).

SPEC sections 2 and 6 declare the verdict lattice CLOSED: every integrity
judgement EMET emits MUST be a member of a fixed, enumerated set, and no
codepath may emit TRUSTED, APPROVED, SAFE, or any value asserting authority.

Before this module the closure was enforced by REVIEW: the tokens were bare
string literals scattered through membrane.py and monitor.py, so emitting an
unsanctioned verdict (e.g. TRUSTED) would have been a review miss, not a
construction error. This module makes the closure STRUCTURAL: every governed
verdict is emitted through governed(), which asserts the token belongs to the
allowed set for its channel and RAISES on a violation. An unsanctioned verdict
therefore fails at construction time, inside the named-core TCB, before a byte
reaches stdout.

This module is part of the named core (SPEC section 10) and depends only on the
language and standard library - in fact on no imports at all. It changes only
HOW a token is emitted, never WHAT: governed() returns the token VERBATIM, so
the surrounding text, spacing, and order at each call site - and thus every
stdout byte - are unchanged. The frozensets below ENUMERATE the governed set;
they do not rename, reorder, or reformat any existing token.

The sets are per CHANNEL because the lattice is layered (SPEC section 2): the
primary integrity lattice is distinct from the closed auxiliary judgements
(coherence, corroboration) and from the governed monitor/audit tokens. None of
these is, or maps to, TRUSTED.
"""

# --- Primary integrity lattice (anchor / verify). SPEC section 2: CLOSED.
# Absence of DRIFT is MATCH or UNVERIFIABLE - never trust.
LATTICE = frozenset({"MATCH", "DRIFT", "UNVERIFIABLE"})

# --- Closed auxiliary judgements (SPEC section 2).
COHERENCE = frozenset({"COHERENT", "VIEW_DIFFERS_FROM_SOURCE", "UNVERIFIABLE"})
CORROBORATE = frozenset({"CORROBORATED", "QUARANTINE_READ_PATH_DIVERGENCE", "UNVERIFIABLE"})

# --- Tamper-evident chain result (SPEC sections 7, 13: chain=INTACT|BROKEN).
AUDIT = frozenset({"INTACT", "BROKEN"})

# --- Portable witness receipt result (SPEC section 17). The stateless offline
# verifier (`emet check`) re-derives a receipt's content address and, optionally,
# its subject digests, and emits exactly one of these. RECEIPT_VALID is a FACT of
# re-derivation (the recorded bytes still hash to the recorded digests, and the
# receipt's own content address is intact), NOT a trust or release decision - it
# maps to no authority word. RECEIPT_TAMPERED is a confirmed divergence (a
# doctored field or a changed subject); RECEIPT_UNVERIFIABLE is an inability to
# check (malformed receipt, missing subject). Like the primary lattice, absence of
# TAMPERED is VALID or UNVERIFIABLE - never trust.
RECEIPT = frozenset({"RECEIPT_VALID", "RECEIPT_TAMPERED", "RECEIPT_UNVERIFIABLE"})

# --- Governed monitor judgements (SPEC section 13 grammar + the monitor report).
# Per-file MATCH / DRIFT / MISSING; per-baseline INTACT / CHANGED. These are the
# exact tokens monitor.py already ships; this change ENUMERATES them as governed
# auxiliary judgements, it does not rename them. (Cross-language conformance
# vectors cover only the membrane commands; monitor governance lives in the SPEC
# and test_monitor.py, never in conformance/vectors.json.)
MONITOR_FILE = frozenset({"MATCH", "DRIFT", "MISSING"})
MONITOR_BASELINE = frozenset({"INTACT", "CHANGED"})

# --- Governed organs judgements (SPEC section 2: organs auxiliary judgements).
# organs.py perception emits per-path UNCHANGED / DRIFTED / NEW / GONE; organs.py
# impedance (gate) emits REVERTIBLE / NOT_REVERTIBLE, the re-derivable FACT that a
# clean operator VCS revert path exists - explicitly NOT a permission to act, and
# mapping to no authority word. These are the exact tokens organs.py ships; this
# change ENUMERATES them as governed auxiliary judgements, it does not rename them.
# (organs is Python-core tooling governed by this spec plus test_organs.py, not by
# the cross-language conformance vectors, so these tokens are pinned here and in
# the SPEC, never in conformance/vectors.json.)
PERCEPTION = frozenset({"UNCHANGED", "DRIFTED", "NEW", "GONE"})
REVERT = frozenset({"REVERTIBLE", "NOT_REVERTIBLE"})

# The full governed universe, for the explicit anti-authority guard below: NO
# channel may admit a token outside this union, and the union excludes every
# authority/permission word by construction.
_ALL = (LATTICE | COHERENCE | CORROBORATE | AUDIT | MONITOR_FILE
        | MONITOR_BASELINE | PERCEPTION | REVERT | RECEIPT)

# Tokens that asserting would breach Boundary 1 (SPEC section 2 / section 6.1).
# Belt-and-suspenders: the channel sets above already exclude these, but pinning
# the denial here makes the intent unmissable and survives a careless edit to a
# channel set.
FORBIDDEN = frozenset({"TRUSTED", "APPROVED", "SAFE", "ALLOWED", "PERMITTED",
                       "AUTHORIZED", "BLESSED", "VERIFIED_AUTHORITY"})


class VerdictError(AssertionError):
    """A codepath tried to emit a token outside its channel's governed set.

    Raised at construction time, inside the TCB, before the token can reach
    stdout - so an unsanctioned verdict is a hard error, not a review miss.
    """


def governed(channel, token):
    """Assert `token` is governed for `channel`; return it VERBATIM.

    `channel` is one of the frozensets above. Returns the token unchanged so the
    caller composes the exact same stdout bytes it always did - this guards WHAT
    is allowed without altering the emitted bytes. Raises VerdictError if the
    token is forbidden outright or is not a member of the channel's closed set.
    """
    if token in FORBIDDEN:
        raise VerdictError(
            "Boundary 1 (SPEC s.2): refused to emit authority verdict "
            + repr(token) + "; the lattice is closed and excludes TRUSTED.")
    if token not in channel:
        raise VerdictError(
            "ungoverned verdict " + repr(token) + " for channel "
            + repr(sorted(channel)) + "; the verdict lattice is closed "
            "(SPEC s.2) - no codepath may emit a token outside it.")
    return token
