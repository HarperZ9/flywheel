"""Eval integrity: a benchmark result is meaningless if the answer leaked.

Harvest of dogfood pass 0085 (arc_agi eval cluster). The load-bearing honesty
gate: a `correct` outcome is contamination, not a pass, when the attempt had
ground-truth access. The same no-overreach-without-disclosure family as the
visual calibration boundary and the optimization dependency boundary.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue


def validate_integrity(result: Any, boundaries: Any, issues: list[Issue]) -> None:
    outcome = result.get("outcome") if isinstance(result, dict) else None
    had_ground_truth = (
        boundaries.get("had_ground_truth") if isinstance(boundaries, dict) else None
    )
    if outcome == "correct" and had_ground_truth is True:
        issues.append(
            Issue(
                "$.boundaries",
                "a 'correct' outcome is contamination, not a pass, when the attempt "
                "had ground-truth access (had_ground_truth=true)",
            )
        )


def has_audit_surface(boundaries: Any, attempt: Any) -> bool:
    """True unless reasoning is declared latent AND no replay ref exists.

    Models that reason in latent loops emit no chain-of-thought transcript; when
    the trace is unavailable, a replay ref is the only remaining audit surface.
    An absent reasoning_trace_available flag is treated as available (opt-in).
    """
    trace = (
        boundaries.get("reasoning_trace_available")
        if isinstance(boundaries, dict)
        else None
    )
    if trace is not False:
        return True
    replay = attempt.get("replay_ref") if isinstance(attempt, dict) else None
    return isinstance(replay, str) and bool(replay.strip())


def validate_auditability(
    result: Any, boundaries: Any, attempt: Any, verdicts: Any, issues: list[Issue]
) -> None:
    """A correct outcome with no audit surface may not be scored MATCH."""
    outcome = result.get("outcome") if isinstance(result, dict) else None
    overall = verdicts.get("overall") if isinstance(verdicts, dict) else None
    if (
        outcome == "correct"
        and overall == "MATCH"
        and not has_audit_surface(boundaries, attempt)
    ):
        issues.append(
            Issue(
                "$.verdicts.overall",
                "a correct outcome with no visible reasoning trace and no replay_ref "
                "has no audit surface; MATCH is not derivable",
            )
        )
