#!/usr/bin/env python3
"""regen_loop.py -- scaffold for the generate-score-regenerate loop.

The higher-order detectors are report-only signals. They earn their keep by
steering revision: a draft is scored, the flagged spans are regenerated toward
specificity, rhythm, and asymmetry, and the result is re-scored. This module is
the SCAFFOLD for that loop, not the loop itself.

What this PR ships and what it does not:

  - score()        real. A thin read over check_text.
  - plan_targets() real. Deterministic mapping from fired signals to the
                   revision directive and the spans a rewrite should touch.
  - run()          skeleton. The control flow is here; the regeneration engine
                   is a caller-supplied seam, `regenerate(text, targets) -> text`.
                   No model is wired in this PR, so with no callback the loop
                   scores once and returns the plan, changing nothing.

Honest-provenance principle (binding on any future wiring):
  - The loop improves writing quality. A lower report score is a byproduct of
    clearer prose, never the target.
  - It MAY attach a receipt of the edits it made (before and after scores, which
    signals cleared), so the change is auditable.
  - Disclosure of AI assistance stays with the end user and is never stripped.
  - It never optimizes to defeat an AI detector. That is a non-goal, stated so
    no reader assumes otherwise.

Standard library only.
"""
from __future__ import annotations

from . import check as _check
from . import profiles as _profiles

LOOP_STAGES = ("draft", "score", "plan", "regenerate", "rescore")

PROVENANCE_NOTE = (
    "Quality loop. A lower report score is a byproduct of clearer writing, not "
    "the target. Edits may carry a receipt; end-user disclosure is never "
    "removed; the loop never optimizes to defeat AI detection.")

# One revision directive per higher-order signal. The directive tells a rewrite
# what to change; the spans come from the signal's own detail.
_DIRECTIVES = {
    "corrective_negation":
        "Recast affirm-then-negate turns as direct claims. Drop the ', not X' "
        "retraction where the positive statement already carries the meaning.",
    "parallel_enumeration":
        "Break the parallel list. Vary item structure or fold items into "
        "sentences; a balanced three-item run especially reads as machine "
        "cadence.",
    "aphoristic_landing":
        "End the paragraph on substance. Cut or rewrite the short final beat "
        "that restates the opening or lands a tag phrase.",
    "repeated_syntactic_frame":
        "Vary sentence openings. Recast the overused frame, and rewrite "
        "pseudo-cleft openers ('What X is', 'It is X that') as direct subjects.",
    "specificity_floor":
        "Raise specificity. Add a name, number, date, or quote to anchorless "
        "paragraphs; replace unsourced-authority and unquantified-magnitude "
        "phrases with a source or a figure; give a bare number its denominator.",
    "rhythm_variance":
        "Vary sentence length and opening part of speech. Break the metronomic "
        "runs so the cadence stops reading as even.",
}


def score(text: str, profile: str = "chat") -> dict:
    """Score `text` under a profile and return its record (gated + report)."""
    return _check.check_text(text, _profiles.load(profile))


def plan_targets(record: dict) -> "list[dict]":
    """Deterministic revision plan from a scored record.

    One target per fired higher-order signal: the signal name, the directive,
    and the detail (spans, metrics) a regeneration step reads to touch only the
    flagged material.
    """
    violations = record.get("violations", {})
    detail = record.get("higher_order", {})
    targets = []
    for signal, directive in _DIRECTIVES.items():
        if violations.get(signal, 0) > 0:
            targets.append({"signal": signal, "count": violations[signal],
                            "directive": directive,
                            "detail": detail.get(signal, {})})
    return targets


def receipt(before: dict, after: dict) -> dict:
    """A before/after edit receipt for one loop round.

    Records the report score movement and which signals cleared. It attests to
    the edit, never to the truth of the prose, and it does not certify a lower
    score as a goal met.
    """
    b_sig = set(before.get("violations", {})) & _sig_names()
    a_sig = set(after.get("violations", {})) & _sig_names()
    return {"before_report_per100w": before.get("report_per100w"),
            "after_report_per100w": after.get("report_per100w"),
            "signals_cleared": sorted(b_sig - a_sig),
            "signals_remaining": sorted(a_sig),
            "provenance": PROVENANCE_NOTE}


def _sig_names() -> set:
    return set(_DIRECTIVES)


def run(text: str, profile: str = "chat", regenerate=None,
        max_rounds: int = 2) -> dict:
    """Scaffold entry point for the generate-score-regenerate loop.

    `regenerate` is the caller-supplied seam, `regenerate(text, targets) -> str`.
    This PR does not wire a model, so with `regenerate=None` the loop scores
    once, returns the plan, and changes nothing. The control flow is here so a
    follow-up wires the engine without redesigning the loop.
    """
    history: "list[dict]" = []
    current = text
    first = None
    for round_i in range(max(1, max_rounds)):
        rec = score(current, profile)
        if first is None:
            first = rec
        targets = plan_targets(rec)
        history.append({"round": round_i,
                        "report_per100w": rec["report_per100w"],
                        "signals": [t["signal"] for t in targets]})
        if not targets or regenerate is None:
            break
        current = regenerate(current, targets)  # caller-supplied, not shipped
    final = score(current, profile)
    return {"text": current, "plan": plan_targets(final),
            "receipt": receipt(first, final), "history": history,
            "stages": LOOP_STAGES, "provenance": PROVENANCE_NOTE}
