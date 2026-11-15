"""Prose renderer for rubric-repair instances.

Renders entirely from the FROZEN entry: the REWARD.md contract prose (shared
verbatim with the rubric-contract family), the broken module inline, the
frozen symptom (observed vs expected on one visible row), and the three
visible expected rows. Eval-time rendering never re-executes anything.
"""

from __future__ import annotations

import json

from .rubric_contract_prompt import DELIVERABLE_PROSE, EMISSION_LINES, contract_lines


def _fixture_line(fx: dict) -> str:
    return (
        f"completion={fx['completion']!r}, answer={fx['answer']!r}, "
        f"info={json.dumps(fx['info'], sort_keys=True)}"
    )


def _outcome_line(label: str, outcome: dict) -> str:
    if "error" in outcome:
        return f"{label} raised: {outcome['error']}"
    metrics = {k: round(v, 4) for k, v in outcome["metrics"].items()}
    return (
        f"{label} reward {round(outcome['reward'], 4)!r}, "
        f"metrics {json.dumps(metrics, sort_keys=True)}"
    )


def render_prompt(entry: dict) -> str:
    lines: list[str] = []
    a = lines.append
    a(
        "A verifiers environment module shipped broken. Repair it so its "
        "Rubric implements EXACTLY the scoring contract below, and reply "
        "with the complete repaired module."
    )
    a("")
    a("## REWARD.md")
    a("")
    a(DELIVERABLE_PROSE)
    a("")
    lines += contract_lines(entry["contract"])
    a("")
    a("## The broken module")
    a("")
    a("```python")
    a(entry["broken_source"].rstrip("\n"))
    a("```")
    a("")
    a("## Observed symptom (frozen from a replay of the broken module)")
    a("")
    symptom = entry["visible"][0]
    a(_fixture_line(symptom["fixture"]))
    a(_outcome_line("-> observed", symptom["observed"]))
    a(_outcome_line("-> expected", symptom["expect"]))
    a("")
    a(
        "## Verified rows (expected behavior; illustrative only; "
        "never scored; values rounded to 4dp)"
    )
    a("")
    for row in entry["visible"]:
        a(_fixture_line(row["fixture"]))
        a(_outcome_line("->", row["expect"]))
        a("")
    a("## Repair policy")
    a("")
    a(
        "Terminal-state scoring grades behavior, not diffs: a behaviorally "
        "equivalent rewrite passes by design. Keep the function names and "
        "the weight vector exactly as REWARD.md states. Hidden fixtures "
        "cover both the broken behavior and behavior the module already got "
        "right, so a rewrite that changes untouched semantics loses credit."
    )
    a("")
    lines += EMISSION_LINES
    return "\n".join(lines)
