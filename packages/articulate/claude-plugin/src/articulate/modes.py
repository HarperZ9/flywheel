#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
articulate.modes -- writing modes: domain style x articulation need.

A mode crosses a DOMAIN register (a base profile) with an ARTICULATION (explain,
persuade, instruct, narrate, argue, prove: what the prose does to the reader). The
`prove` articulation makes a proof legible for a reader; it never means the tool
verified the theorem. A mode is
the base profile plus a small delta: an optional slop override, terms of art to
keep, categories to gate even under a flavored base (gate_promote), and editor
guidance. Adding a mode is adding one record, not editing the engine.

A mode tunes style WITHIN the plain-writing standard. It may tighten the gate and
add terms of art. It may not re-enable a banned HIGH device, with one exception:
literary narrative maps to slop=off, where authorial voice governs and nothing
gates. Detection and quality only; never evasion.

Source: the domain x articulation study (2026-09-17). Two proposed detector
categories (legalese-archaism, unproven-claim) are noted where a mode wants them
and are deferred until their patterns ship. Standard library only.
"""
from __future__ import annotations

from . import detector, profiles


class ModeError(ValueError):
    """An unknown or malformed mode."""


def _m(base, articulation, *, slop=None, keep_add=(), gate_promote=(),
       weights=(), require_fix=(), standard_delta="", run_fix_by_default=True):
    return {
        "base": base,
        "articulation": articulation,
        "slop": slop,                       # None inherits the base profile's slop
        "keep_add": tuple(keep_add),
        "gate_promote": tuple(gate_promote),  # detector categories that block
        "editor": {
            "weights": tuple(weights),       # bias the polish `worst` pick + the bar
            "require_fix": tuple(require_fix),  # LOW advisories the fix loop must clear
            "standard_delta": standard_delta,   # one line appended to the editor STANDARD
            "run_fix_by_default": run_fix_by_default,
        },
    }


# The five reusable articulation overlays are folded into each record below.
MODES: dict[str, dict] = {
    "technical-docs/explain": _m(
        "api-docs", "explain",
        weights=("concreteness", "restatable"),
        require_fix=("nominalization", "expletive-opener"),
        standard_delta="Give every named object a one-sentence definition on first use; put a runnable example beside each claim."),
    "technical-docs/instruct": _m(
        "procedure", "instruct",
        require_fix=("expletive-opener",), weights=("economy", "commitment"),
        standard_delta="Every line is a command or a stated precondition; one action per step; end on the observable result."),
    "technical-docs/argue": _m(
        "normative-spec", "argue", gate_promote=("unsupported-authority",),
        weights=("commitment", "restatable"),
        standard_delta="State the decision plainly; name each rejected alternative and the reason."),
    "persuasive-essay/persuade": _m(
        "essay", "persuade", weights=("concreteness", "economy", "rhythm", "commitment"),
        standard_delta="Trace one throughline; each paragraph narrows it with a new case or extends its stake with a new consequence."),
    "persuasive-essay/argue": _m(
        "essay", "argue", gate_promote=("unsupported-authority",),
        keep_add=("steelman", "counterargument", "rebuttal"),
        weights=("commitment", "concreteness", "rhythm"),
        standard_delta="Each section: thesis, named example, the opposing case in its strongest form, named refutation."),
    "academic/explain": _m(
        "research", "explain",
        keep_add=("robust", "robustness", "significant", "significance"),
        weights=("concreteness", "restatable"),
        standard_delta="Every paragraph leaves a named instrument, dataset, or measured value; preserve every unit, N, p-value, and CI verbatim."),
    "academic/argue": _m(
        "research", "argue", gate_promote=("unsupported-authority",),
        weights=("commitment", "restatable"),
        standard_delta="Flag any finding stated without its meaning; one calibrated hedge per claim, never two stacked."),
    # Proof-architecture mode: makes a hard proof legible for a reader. It screens
    # prose only and asserts nothing about whether the theorem is correct. run_fix
    # is off by default: a wrong rewrite of a quantifier order or an inequality
    # direction changes a theorem's truth, so it routes to --judge, and --fix is opt-in.
    "academic/prove": _m(
        "proof", "prove",
        keep_add=("theorem", "lemma", "corollary", "proposition", "hypothesis",
                  "monotone", "compact", "at scale", "surface area", "crux",
                  "manifold", "eigenvalue", "vorticity"),
        weights=("concreteness", "restatable"), run_fix_by_default=False,
        standard_delta=(
            "State the idea in one paragraph before the formal statement and label "
            "it Idea. Open with a roadmap that names each lemma in the order it is "
            "used. Define every symbol once at first use and never rename it. "
            "Preserve every hypothesis, quantifier and its order, inequality "
            "direction, and constant-dependence clause exactly. Write a contrast as "
            "two plain sentences. Label a sketch Sketch and a full argument Proof, "
            "and keep a sketch's confidence out of the formal section. A calibrated "
            "does-not-prove line is precision; keep it. Commitment here targets "
            "sentence construction, never the truth of the result. This mode screens "
            "prose only and asserts nothing about whether the theorem is correct.")),
    # Long-form intuition register: a Tao-blog or Quanta-style companion to a formal
    # result. Built on research so scientific vocabulary reports without gating.
    # Rewrites are allowed, but the editor masks every math span first, so a formula
    # is preserved byte for byte. Exposition only; it makes no correctness claim.
    "science-writing/explain": _m(
        "research", "explain",
        keep_add=("theorem", "lemma", "at scale", "surface area", "crux",
                  "manifold", "eigenvalue", "vorticity"),
        weights=("concreteness", "restatable"),
        standard_delta=(
            "Give the informal picture before the formal object, and name the object "
            "only after the reader has seen what it does. Run the argument on a small "
            "case first. Where a naive argument breaks, say where. State any analogy "
            "with its scope of validity, and keep the precise statement beside an "
            "informally-marked gloss. This is exposition and makes no correctness claim.")),
    "journalism/explain": _m(
        "journalism", "explain", slop="strict",
        weights=("economy", "concreteness", "commitment"),
        require_fix=("closer", "meta"),
        standard_delta="Inverted pyramid: the lede answers the question; attribute every claim or cut it; no closer."),
    "journalism/narrate": _m(
        "journalism", "narrate",
        keep_add=("recalled", "watched"),
        weights=("rhythm", "concreteness"),
        require_fix=("cadence-uniform",),
        standard_delta="Every sensory claim traces to something witnessed or sourced; the nut graf appears once, after the opening scene."),
    "legal/explain": _m(
        "legal", "explain", gate_promote=("unsupported-authority",),
        weights=("concreteness", "restatable"),
        standard_delta="Every duty and deadline gets a named party and a specific date or trigger. (Proposed: a legalese-archaism category.)"),
    "legal/instruct": _m(
        "legal", "instruct", require_fix=("hedge-stack", "vague-quantifier"),
        weights=("commitment", "economy"),
        standard_delta="One obligation per sentence; condition, obligation, consequence; cut doublets and triplets."),
    "legal/argue": _m(
        "legal", "argue", slop="strict", gate_promote=("unsupported-authority",),
        weights=("commitment", "concreteness"),
        standard_delta="An unstated ask is top severity; name the controlling case or statute in the same sentence as the rule."),
    "marketing/persuade": _m(
        "social", "persuade", slop="strict",
        keep_add=("conversion", "funnel", "positioning"),
        weights=("commitment", "concreteness"),
        standard_delta="Every benefit claim carries a number, mechanism, or comparison in the same or next sentence, or the adjective is cut. (Proposed: unproven-claim + a proof-density quality.)"),
    "marketing/explain": _m(
        "api-docs", "explain", gate_promote=("marketing", "register-word"),
        weights=("concreteness", "restatable"),
        standard_delta="Every mechanism claim carries a worked example, a real number, or a named limitation; if the source has none, flag it, never invent one."),
    "marketing/narrate": _m(
        "social", "narrate", gate_promote=("marketing", "register-word"),
        require_fix=("cadence-uniform",), weights=("rhythm", "concreteness"),
        standard_delta="The customer, not the brand, is the subject; open on the before-state, close on a specific checkable after-state, not a tagline."),
    "tutorial/instruct": _m(
        "procedure", "instruct", weights=("economy", "commitment"),
        standard_delta="One verb per step, a verification line after each step, a stated end-state before step 1; strip any step that changes no observable state."),
    "tutorial/explain": _m(
        "flavored", "explain",
        require_fix=("nominalization", "expletive-opener"),
        weights=("concreteness", "restatable"),
        standard_delta="Worked example before the abstraction; no term used before it is defined."),
    "memo/explain": _m(
        "essay", "explain", weights=("commitment", "restatable"),
        require_fix=("closer",),
        standard_delta="SCQA order; one claim per paragraph stated first; every data point preceded by the claim it supports; no decorative bullets."),
    "memo/instruct": _m(
        "procedure", "instruct", weights=("commitment", "economy"),
        require_fix=("expletive-opener",),
        standard_delta="BLUF: action first, then owner and deadline, then context; one named owner and date per item; no passive 'should be completed'."),
    "memo/argue": _m(
        "essay", "argue", weights=("commitment", "restatable"),
        standard_delta="Decision and ask in sentence one; a named-alternatives comparison must attach a number or consequence to each side; close on the action and deadline."),
    "narrative/narrate": _m(
        "narrative", "narrate", slop="off",
        weights=("rhythm", "concreteness"), run_fix_by_default=False,
        standard_delta="Authorial voice governs; nothing gates. Route to --judge, not --fix; a model-picked replacement word is itself the contamination."),
    # The genre axis: narrative and expressive prose, read by its own convention.
    "literary-fiction/narrate": _m(
        "literary-fiction", "narrate",
        weights=("rhythm", "concreteness"), run_fix_by_default=False,
        standard_delta="Voice governs; nothing gates. Report the fiction lexicon as optional review; observe, do not rewrite."),
    "genre-fiction/narrate": _m(
        "genre-fiction", "narrate",
        weights=("rhythm", "concreteness"), run_fix_by_default=False,
        standard_delta="Voice governs; keep genre convention phrasing. Flag the fiction lexicon as advisory, never a defect."),
    "ya-fiction/narrate": _m(
        "ya-fiction", "narrate",
        weights=("rhythm", "concreteness"), run_fix_by_default=False,
        standard_delta="Voice governs; nothing gates. The fiction lexicon is advisory only."),
    "memoir/narrate": _m(
        "memoir", "narrate",
        weights=("rhythm", "concreteness", "commitment"), run_fix_by_default=False,
        standard_delta="Interiority is the form; nothing gates. Never rescore or rewrite a recalled quote; it is testimony, not prose to fix."),
    "screenplay/narrate": _m(
        "screenplay", "narrate",
        weights=("economy", "concreteness"), run_fix_by_default=False,
        standard_delta="Action lines stay present-tense and filmable; the device gate holds there. Dialogue keeps the character's voice and is exempt."),
    "poetry/express": _m(
        "poetry", "narrate",
        weights=("rhythm",), run_fix_by_default=False,
        standard_delta="The line is the unit; craft devices are technique, not flaws. Make no claim to detect a machine hand in verse."),
}


def load(mode_id: str) -> dict:
    """Resolve a mode to a profile-like dict the detector consumes: slop, keep,
    gate_promote, register, plus editor guidance. Fails closed on an unknown mode
    or an unknown promoted category."""
    m = MODES.get(mode_id)
    if m is None:
        raise ModeError(
            f"unknown mode {mode_id!r}; known: {', '.join(sorted(MODES))}")
    base = profiles.load(m["base"])
    promote = tuple(m["gate_promote"])
    bad = set(promote) - detector.known_categories()
    if bad:
        raise ModeError(
            f"mode {mode_id!r} promotes unknown categories: {sorted(bad)}")
    out = {
        "slop": m["slop"] or base["slop"],
        "keep": tuple(base.get("keep", ())) + tuple(m["keep_add"]),
        "gate_promote": promote,
        "register": base.get("register"),
        "mode_id": mode_id,
        "articulation": m["articulation"],
        "editor": dict(m["editor"]),
    }
    # A genre base (literary-fiction, screenplay, poetry, ...) carries the genre
    # fields the detector reads. Pass them through so a genre mode behaves like
    # its genre. A plain register base carries none of these, so nothing changes.
    for k in ("genre", "unit", "structural_classify", "dialogue_exempt",
              "quote_exempt_all", "fiction_slop", "suppress_categories"):
        if k in base:
            out[k] = base[k]
    return out


def names():
    return sorted(MODES)
