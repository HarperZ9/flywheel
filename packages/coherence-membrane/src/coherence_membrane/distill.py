"""distill: verified compression of code (and later prose), as graders on refine.

Compression is criterion-preserving: a candidate is accepted only when the
declared criterion survives. The model proposes; these deterministic graders
verify. No model in the checking step.
"""
from __future__ import annotations

import hashlib
import subprocess

from .refine import GradedCriterion, refine


def readability_cost(text: str) -> float:
    """A deterministic reconstruction-time proxy. Lower is easier to read.

    The cost is the sum of each line's length SQUARED. Squaring makes a long,
    crammed line cost far more than the same characters split across clear lines:
    splitting an 80-column line into two 40-column lines drops the cost (rewarded),
    joining them back raises it (penalized). So a code-golfed candidate (logic
    crammed onto few long lines) scores worse than a clear multi-line one, while a
    short concise line is not punished. Indentation contributes mildly through line
    length, with no perverse reward for nesting. Language-agnostic; refined later.

    Bound: this proxy measures line geometry only; it does not detect identifier
    crypticness, comment removal counted as a density win, or control-flow
    complexity, which are deferred metrics.
    """
    return float(sum(len(line) ** 2 for line in text.splitlines()))


def _ratio_deviation(numerator_of_candidate, original_value: float):
    """A deviation = candidate_value / original_value. >=0; ideal < 1; >= 1 fails
    at tolerance 1.0. Fail-closed: a zero or negative original yields inf (refine's
    grade then reads it as unmeasurable, never a false pass)."""
    def deviation(candidate_text: str) -> float:
        if original_value <= 0:
            return float("inf")
        return numerator_of_candidate(candidate_text) / original_value
    return deviation


def density_grader(original_bytes: int) -> GradedCriterion:
    return GradedCriterion(
        "density", "objective",
        _ratio_deviation(lambda t: len(t.encode("utf-8")), float(original_bytes)),
        1.0,
    )


def readability_grader(original_cost: float) -> GradedCriterion:
    return GradedCriterion(
        "readability", "objective",
        _ratio_deviation(readability_cost, original_cost),
        1.0,
    )


def command_guard(cmd, timeout: float = 300.0):
    """A hard guard that runs a behavior check (typically the test suite). True
    only on exit 0. cmd=None leaves behavior unchecked (always True). Fail-closed:
    any launch or timeout error is False, never a false pass. The caller is
    responsible for arranging that cmd exercises the candidate."""
    def guard(_candidate) -> bool:
        if cmd is None:
            return True
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout).returncode == 0
        except Exception:
            return False
    return guard


def distill_code(original: str, *, propose=None, candidate=None, behavior_guard=None, max_iter=1) -> dict:
    """Compress original while preserving its criterion.

    Verdict contract:
    - ACCEPTED: the criterion is preserved (refine status is correct). This includes
      the zero-gain boundary where candidate_bytes >= original_bytes; see `compressed`.
    - REJECTED: a candidate was produced but failed at least one grader or the
      behavior guard.
    - UNVERIFIABLE: no candidate was produced (generate raised or returned None).

    `behavior_checked` is False when no behavior_guard was supplied, meaning the
    behavior axis was not exercised; the verdict reflects only the grader axes.
    """
    if (propose is None) == (candidate is None):
        raise ValueError("distill_code: pass exactly one of propose= or candidate=")
    original_bytes = len(original.encode("utf-8"))
    original_cost = readability_cost(original)
    graders = [density_grader(original_bytes), readability_grader(original_cost)]
    guard = behavior_guard if behavior_guard is not None else command_guard(None)
    generate = propose if propose is not None else (lambda _state: candidate)
    outcome = refine(
        generate, graders, adjust=lambda _r, s: s, guard=guard,
        target_margin=0.0, cohesion_bar=0.0, max_iter=max_iter,
    )
    cand = outcome.candidate if outcome.candidate is not None else ""
    cand_bytes = len(cand.encode("utf-8"))
    if outcome.status == "correct":
        verdict = "ACCEPTED"
    elif cand:
        verdict = "REJECTED"
    else:
        verdict = "UNVERIFIABLE"
    gain = round(original_bytes / cand_bytes, 3) if cand_bytes else None
    return {
        "schema": "coherence.distill/1",
        "verdict": verdict,
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(cand.encode("utf-8")).hexdigest() if cand else None,
        "original_bytes": original_bytes,
        "candidate_bytes": cand_bytes,
        "gain": gain,
        "compressed": gain is not None and gain > 1.0,
        "readability_before": round(original_cost, 3),
        "readability_after": round(readability_cost(cand), 3) if cand else None,
        "short_axis": outcome.short_axis,
        "behavior_checked": behavior_guard is not None,
        "recheck": "python -m coherence_membrane distill --code --original <original> --candidate <candidate>",
    }
